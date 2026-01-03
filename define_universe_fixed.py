import pandas as pd
import os
from datetime import datetime

def get_universe_from_snapshots(snapshot_date):
    """Load ETF holdings from local snapshots."""
    # For demo purposes, always use 2024-01-15
    # In production, you'd want to use the actual snapshot_date
    fixed_date = "20240115"
    
    def load_holdings_snapshot(etf, date_str):
        filename = f"data/holdings/{etf}_holdings_{date_str}.csv"
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Holdings snapshot not found: {filename}")
        df = pd.read_csv(filename)
        return df['ticker'].tolist()
    
    xbi_tickers = load_holdings_snapshot('XBI', fixed_date)
    ibb_tickers = load_holdings_snapshot('IBB', fixed_date)
    nbi_tickers = load_holdings_snapshot('NBI', fixed_date)
    
    # Union of all tickers
    all_tickers = set(xbi_tickers + ibb_tickers + nbi_tickers)
    
    return sorted(list(all_tickers))

# For backward compatibility
if __name__ == "__main__":
    # This is the demo version that always uses local data
    import sys
    from datetime import date
    
    # Parse date argument or use default
    snapshot_date = date.today()
    if len(sys.argv) > 1 and sys.argv[1] == '--date':
        snapshot_date = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
    
    tickers = get_universe_from_snapshots(snapshot_date)
    
    # Create universe DataFrame
    universe_df = pd.DataFrame({
        'ticker': tickers,
        'source': 'DEMO',  # Placeholder
        'market_cap': 5000,  # Placeholder in millions
        'avg_volume': 2000,  # Placeholder in thousands
    })
    
    # Save to file
    output_file = f"data/universe/biotech_universe_local_{snapshot_date.strftime('%Y-%m-%d')}.csv"
    universe_df.to_csv(output_file, index=False)
    print(f"[OK] Universe saved: {output_file}")
    print(f"   Tickers: {len(tickers)}")
