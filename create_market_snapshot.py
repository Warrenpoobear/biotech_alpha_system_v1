"""
Market Snapshot Module - Deterministic Market Data Layer
Saves price, volume, market cap, ADV for universe tickers.
"""
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import sys
import os
import hashlib
from typing import List

class MarketSnapshot:
    """Deterministic market data snapshot for a specific date."""
    
    def __init__(self, date_str: str, universe_file: str):
        self.date = datetime.strptime(date_str, "%Y-%m-%d")
        self.date_str = date_str
        self.universe_file = universe_file
        self.snapshot_dir = "data/snapshots"
        os.makedirs(self.snapshot_dir, exist_ok=True)
        
    def load_universe(self) -> pd.DataFrame:
        """Load deterministic universe."""
        df = pd.read_csv(self.universe_file)
        # define_universe_v2.py emits `ticker`
        return df[['ticker']]
    
    def fetch_market_data(self, tickers: List[str]) -> pd.DataFrame:
        """
        Fetch market data for tickers up to snapshot date.
        Uses yfinance with deterministic period.
        """
        # Go back 60 days for 20-day moving averages
        start_date = self.date - timedelta(days=60)
        
        market_data = []
        for ticker in tickers:
            try:
                # Download with explicit period
                stock = yf.Ticker(ticker)
                hist = stock.history(
                    start=start_date.strftime("%Y-%m-%d"),
                    end=(self.date + timedelta(days=1)).strftime("%Y-%m-%d"),
                    auto_adjust=False,
                )
                
                if hist.empty:
                    print(f"  [WARN] No data for {ticker}")
                    continue
                
                # take last trading day <= as_of
                hist = hist.loc[hist.index.date <= self.date.date()]
                snapshot_row = hist.iloc[-1] if len(hist) > 0 else None
                if snapshot_row is None:
                    continue
                
                # Calculate 20-day average volume
                if len(hist) >= 20:
                    adv_20 = hist['Volume'].tail(20).mean()
                else:
                    adv_20 = hist['Volume'].mean()
                
                market_data.append({
                    'ticker': ticker,
                    'as_of_date': self.date_str,
                    'close': float(snapshot_row['Close']),
                    'volume': int(snapshot_row['Volume']),
                    'adv_20': float(adv_20),
                })
                
            except Exception as e:
                print(f"  [ERROR] {ticker}: {str(e)[:100]}")
                continue
        
        df = pd.DataFrame(market_data)
        if df.empty:
            return df
        # canonical column order + deterministic row order
        df = df[['ticker','as_of_date','close','volume','adv_20']].sort_values(['ticker']).reset_index(drop=True)
        return df
    
    def create_snapshot(self) -> str:
        """Create and save deterministic market snapshot."""
        print(f"\n[1] Creating Market Snapshot for {self.date_str}")
        print("-" * 50)
        
        snapshot_file = f"{self.snapshot_dir}/market_{self.date_str}.csv"
        hash_file = f"{self.snapshot_dir}/market_{self.date_str}.sha256"
        # FAIL-CLOSED: never refetch if snapshot already exists
        if os.path.exists(snapshot_file) and os.path.exists(hash_file):
            print(f"   [OK] Snapshot exists (no refetch): {snapshot_file}")
            return snapshot_file
        
        universe_df = self.load_universe()
        tickers = universe_df['ticker'].tolist()
        print(f"   Tickers: {len(tickers)} from {self.universe_file}")
        
        # Fetch market data
        print(f"   Fetching market data (60-day window)...")
        market_df = self.fetch_market_data(tickers)
        
        if market_df.empty:
            print(f"   [ERROR] No market data retrieved")
            return None
        
        # Save canonical CSV (LF endings, stable floats)
        market_df.to_csv(snapshot_file, index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f")
        # Hash the exact bytes on disk (strongest determinism contract)
        with open(snapshot_file, "rb") as f:
            snapshot_bytes = f.read()
        snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
        
        # Write ONLY the hash (no timestamps)
        with open(hash_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"{snapshot_hash}\n")
        
        print(f"   [OK] Snapshot saved: {snapshot_file}")
        print(f"        Tickers: {len(market_df)}")
        print(f"        SHA256: {snapshot_hash[:16]}...")
        print(f"        Close range: ${market_df['close'].min():.2f} - ${market_df['close'].max():.2f}")
        print(f"        Volume range: {market_df['volume'].min():,} - {market_df['volume'].max():,}")
        
        return snapshot_file

def main():
    """Command-line interface."""
    import argparse
    parser = argparse.ArgumentParser(description='Create deterministic market snapshot')
    parser.add_argument('--date', type=str, required=True, help='Snapshot date (YYYY-MM-DD)')
    parser.add_argument('--universe', type=str, default='data/universe/biotech_universe_local_2024-01-15.csv',
                       help='Universe CSV file')
    
    args = parser.parse_args()
    
    snapshot = MarketSnapshot(args.date, args.universe)
    snapshot_file = snapshot.create_snapshot()
    
    if snapshot_file:
        print(f"\n[OK] Market snapshot complete: {snapshot_file}")
        return 0
    else:
        print(f"\n[ERROR] Market snapshot failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
