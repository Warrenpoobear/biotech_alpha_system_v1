"""
WAKE ROBIN BIOTECH UNIVERSE v2.0
Reads from local holdings snapshots for complete determinism.
"""
import pandas as pd
from datetime import date
import hashlib
import os
from typing import List, Set

def load_holdings_snapshot(etf: str, snapshot_date: date) -> List[str]:
    """Load holdings from local CSV snapshot."""
    filename = f"data/holdings/{etf.lower()}_holdings_{snapshot_date.strftime('%Y%m%d')}.csv"
    
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Holdings snapshot not found: {filename}")
    
    df = pd.read_csv(filename)
    return df['ticker'].tolist()

def get_universe_from_snapshots(snapshot_date: date = None) -> pd.DataFrame:
    """Get deterministic universe from local holdings snapshots."""
    if snapshot_date is None:
        snapshot_date = date(2024, 1, 15)
    
    # Load from local snapshots
    xbi_tickers = load_holdings_snapshot('XBI', snapshot_date)
    ibb_tickers = load_holdings_snapshot('IBB', snapshot_date)
    nbi_tickers = load_holdings_snapshot('NBI', snapshot_date)
    
    # Union of all tickers
    all_tickers: Set[str] = set()
    all_tickers.update(xbi_tickers)
    all_tickers.update(ibb_tickers)
    all_tickers.update(nbi_tickers)
    
    # Create universe dataframe
    universe = pd.DataFrame(sorted(all_tickers), columns=['ticker'])
    universe['snapshot_date'] = snapshot_date.isoformat()
    universe['source'] = 'XBI_IBB_NBI_v2_local'
    
    # Add source flags
    universe['in_xbi'] = universe['ticker'].isin(xbi_tickers)
    universe['in_ibb'] = universe['ticker'].isin(ibb_tickers)
    universe['in_nbi'] = universe['ticker'].isin(nbi_tickers)
    
    # Mock market data (in production, you'd fetch real data)
    # For determinism, we'll use fixed values based on ticker hash
    def mock_market_cap(ticker: str) -> float:
        """Generate deterministic mock market cap."""
        ticker_hash = int(hashlib.md5(ticker.encode()).hexdigest()[:8], 16)
        return 1000 + (ticker_hash % 9000)  # Between 1B and 10B
    
    def mock_volume(ticker: str) -> float:
        """Generate deterministic mock volume."""
        ticker_hash = int(hashlib.md5(ticker.encode()).hexdigest()[:8], 16)
        return 500 + (ticker_hash % 4500)  # Between 500k and 5M
    
    universe['market_cap'] = universe['ticker'].apply(mock_market_cap)
    universe['avg_volume'] = universe['ticker'].apply(mock_volume)
    
    # Filter for size and liquidity
    universe = universe[
        (universe['market_cap'] > 2000) &  # > $2B market cap
        (universe['avg_volume'] > 1000)    # > 1M average volume
    ].copy()
    
    # Deterministic, cross-platform universe hash
    tickers = universe["ticker"].tolist()  # already sorted
    ubytes = ("\n".join(tickers)).encode("utf-8")
    universe_hash = hashlib.sha256(ubytes).hexdigest()
    universe["universe_hash"] = universe_hash
    
    return universe

def save_deterministic_universe(snapshot_date: date = None):
    """Save deterministic universe to CSV for audit trail."""
    if snapshot_date is None:
        snapshot_date = date(2024, 1, 15)
    
    universe = get_universe_from_snapshots(snapshot_date)
    
    # Create output directory
    os.makedirs('data/universe', exist_ok=True)
    
    # Deterministic filename based on snapshot_date
    snap = snapshot_date.isoformat()
    filename = f"data/universe/biotech_universe_local_{snap}.csv"
    
    # LF-only line endings for cross-platform byte identity
    universe.to_csv(filename, index=False, encoding="utf-8", lineterminator="\n")
    
    # Also save a hash file for verification
    universe_hash = universe["universe_hash"].iloc[0]
    hash_path = f"data/universe/universe_hash_local_{snap}.txt"
    with open(hash_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"Hash: {universe_hash}\n")
        f.write(f"Tickers: {len(universe)}\n")
        f.write(f"Snapshot: {snap}\n")
        f.write(f"Sources: XBI, IBB, NBI local snapshots\n")
    
    # Print summary
    print(f"[OK] Universe saved: {filename}")
    print(f"   Tickers: {len(universe)}")
    print(f"   Hash: {universe_hash}")
    print(f"   Market Cap Range: ${universe['market_cap'].min():,.0f}M - ${universe['market_cap'].max():,.0f}M")
    print(f"   Volume Range: {universe['avg_volume'].min():,.0f}k - {universe['avg_volume'].max():,.0f}k")
    
    return universe

if __name__ == '__main__':
    universe = save_deterministic_universe()
    print("\nFirst 10 tickers with sources:")
    for _, row in universe.head(10).iterrows():
        sources = []
        if row['in_xbi']: sources.append('XBI')
        if row['in_ibb']: sources.append('IBB')
        if row['in_nbi']: sources.append('NBI')
        print(f"  {row['ticker']}: {', '.join(sources)}")
    
    print(f"\nTotal tickers: {len(universe)}")
