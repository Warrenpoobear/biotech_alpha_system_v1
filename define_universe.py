"""
WAKE ROBIN BIOTECH UNIVERSE v1.0
XBI + IBB + NBI union, filtered for liquidity.
Freeze: provided by snapshot_date argument (no runtime timestamps in-file)
"""
import pandas as pd
from datetime import date
import hashlib
import os

# Core ETF holdings (static snapshot for determinism)
XBI_HOLDINGS = [
    'AMGN', 'GILD', 'VRTX', 'REGN', 'BIIB', 'MRNA', 
    'ILMN', 'ALNY', 'BMRN', 'SRPT', 'EXAS', 'NTRA',
    'TWST', 'BEAM', 'CRSP', 'EDIT', 'VERV', 'KYMR'
]

IBB_HOLDINGS = [
    'AMGN', 'GILD', 'VRTX', 'REGN', 'BIIB', 'MRNA',
    'ILMN', 'ALNY', 'BMRN', 'SGEN', 'INCY', 'EXEL',
    'NBIX', 'UTHR', 'IONS', 'ARWR', 'BLUE', 'RARE'
]

NBI_HOLDINGS = [
    'AMGN', 'GILD', 'VRTX', 'REGN', 'BIIB', 'MRNA',
    'ILMN', 'ALNY', 'BMRN', 'EXAS', 'NTRA', 'TWST',
    'BEAM', 'CRSP', 'EDIT', 'VERV', 'KYMR', 'AKRO'
]

def get_universe_snapshot(snapshot_date: date = None) -> pd.DataFrame:
    """Get deterministic universe snapshot."""
    if snapshot_date is None:
        snapshot_date = date(2024, 1, 15)  # deterministic default (override in live runs)
    
    # Union of all tickers
    all_tickers = set(XBI_HOLDINGS + IBB_HOLDINGS + NBI_HOLDINGS)
    
    # Create universe dataframe
    universe = pd.DataFrame(sorted(all_tickers), columns=['ticker'])
    universe['snapshot_date'] = snapshot_date.isoformat()
    universe['source'] = 'XBI_IBB_NBI_v1'
    
    # Add basic metadata (mocked for now - would come from yfinance)
    # In production, you'd fetch market cap and volume here
    universe['market_cap'] = 5000  # Mock in millions
    universe['avg_volume'] = 2000  # Mock in thousands
    
    # Filter for size and liquidity (mocked)
    universe = universe[
        (universe['market_cap'] > 200) & 
        (universe['avg_volume'] > 1000)
    ].copy()
    
    # Deterministic, cross-platform universe hash (no Python hash randomization)
    tickers = universe["ticker"].tolist()  # already sorted
    ubytes = ("\n".join(tickers)).encode("utf-8")
    universe_hash = hashlib.sha256(ubytes).hexdigest()
    universe["universe_hash"] = universe_hash
    
    return universe

def save_universe_to_csv():
    """Save deterministic universe to CSV for audit trail."""
    universe = get_universe_snapshot()
    
    # Create output directory
    os.makedirs('data/universe', exist_ok=True)
    
    # Deterministic filename based on snapshot_date (not wall-clock)
    snap = universe["snapshot_date"].iloc[0]
    filename = f"data/universe/biotech_universe_{snap}.csv"
    
    # LF-only line endings for cross-platform byte identity
    universe.to_csv(filename, index=False, encoding="utf-8", lineterminator="\n")
    
    # Also save a hash file for verification
    universe_hash = universe["universe_hash"].iloc[0]
    hash_path = f"data/universe/universe_hash_{snap}.txt"
    with open(hash_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"Hash: {universe_hash}\n")
        f.write(f"Tickers: {len(universe)}\n")
        f.write(f"Snapshot: {snap}\n")
    
    print(f"✅ Universe saved: {filename}")
    print(f"   Tickers: {len(universe)}")
    print(f"   Hash: {universe_hash}")
    
    return universe

if __name__ == '__main__':
    universe = save_universe_to_csv()
    print("\nFirst 10 tickers:")
    print(universe['ticker'].head(10).tolist())
