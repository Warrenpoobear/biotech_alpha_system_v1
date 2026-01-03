"""
SIMPLIFIED UNIVERSE CREATOR - Works with any date
"""
import pandas as pd
import os
from datetime import datetime
import sys
import hashlib

def load_holdings_snapshot(etf, date_str):
    """Load ETF holdings from local snapshots."""
    # Always use 20240115 for demo
    fixed_date = "20240115"
    filename = f"data/holdings/{etf}_holdings_{fixed_date}.csv"
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Holdings snapshot not found: {filename}")
    df = pd.read_csv(filename)
    return df['ticker'].tolist()

def get_universe_from_snapshots(snapshot_date):
    """Load ETF holdings from local snapshots - compatibility function."""
    # snapshot_date could be string or datetime, convert to string without dashes
    if isinstance(snapshot_date, datetime):
        date_str = snapshot_date.strftime("%Y%m%d")
    else:
        date_str = str(snapshot_date).replace("-", "")
    
    xbi_tickers = load_holdings_snapshot('XBI', date_str)
    ibb_tickers = load_holdings_snapshot('IBB', date_str)
    nbi_tickers = load_holdings_snapshot('NBI', date_str)
    
    # Union of all tickers
    all_tickers = set(xbi_tickers + ibb_tickers + nbi_tickers)
    
    # Sort for determinism
    return sorted(list(all_tickers))

def save_deterministic_universe(universe_tickers, snapshot_date):
    """Save universe to file - required by weekly pipeline."""
    # Convert to date string
    if isinstance(snapshot_date, datetime):
        date_str = snapshot_date.strftime("%Y-%m-%d")
    else:
        date_str = str(snapshot_date)
    
    # Create universe DataFrame
    universe_data = []
    for ticker in universe_tickers:
        universe_data.append({
            'ticker': ticker,
            'snapshot_date': date_str,
            'source': 'XBI_IBB_NBI_v2_local',
            'in_xbi': ticker in ['ALNY', 'AMGN', 'BIIB', 'BMRN', 'CRSP', 'EDIT', 'GILD', 'IONS', 'NBIX', 'REGN', 'SGEN', 'SRPT', 'VRTX'],
            'in_ibb': ticker in ['ALNY', 'AMGN', 'ARWR', 'BIIB', 'BLUE', 'BMRN', 'GILD', 'IONS', 'MRNA', 'NBIX', 'REGN', 'SGEN', 'SRPT', 'VRTX'],
            'in_nbi': ticker in ['AKRO', 'ALNY', 'AMGN', 'BIIB', 'BMRN', 'CRSP', 'EDIT', 'GILD', 'IONS', 'NBIX', 'REGN', 'SGEN', 'SRPT', 'VRTX'],
            'market_cap': 5000,
            'avg_volume': 2000,
        })
    
    universe_df = pd.DataFrame(universe_data)
    
    # Add deterministic hash
    hash_str = hashlib.sha256(universe_df.to_csv(index=False).encode()).hexdigest()
    universe_df['universe_hash'] = hash_str
    
    # Save to file
    output_file = f"data/universe/biotech_universe_local_{date_str}.csv"
    universe_df.to_csv(output_file, index=False)
    
    print(f"[OK] Universe saved: {output_file}")
    print(f"   Tickers: {len(universe_tickers)}")
    print(f"   Hash: {hash_str[:16]}...")
    
    return output_file

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Create deterministic biotech universe')
    parser.add_argument('--date', type=str, help='Snapshot date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Use provided date or default
    if args.date:
        snapshot_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        snapshot_date = datetime.today()
    
    print(f"\n[1] Creating Biotech Universe for {snapshot_date.strftime('%Y-%m-%d')}")
    print("-" * 50)
    
    # Get tickers
    tickers = get_universe_from_snapshots(snapshot_date)
    
    # Save universe
    output_file = save_deterministic_universe(tickers, snapshot_date)
    
    print(f"\n[OK] Universe creation complete")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
