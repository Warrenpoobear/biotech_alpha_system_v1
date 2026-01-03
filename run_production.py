import sys
import os
from datetime import date, timedelta, datetime
import argparse

def get_previous_friday(run_date: date) -> date:
    """Return the previous Friday for a given date."""
    days_since_friday = (run_date.weekday() - 4) % 7
    return run_date if days_since_friday == 0 else (run_date - timedelta(days=days_since_friday))

def main():
    parser = argparse.ArgumentParser(description="Run the Wake Robin production pipeline.")
    parser.add_argument('--date', type=str, help='Run date in YYYY-MM-DD format (default: previous Friday)')
    parser.add_argument('--mode', type=str, default='demo', choices=['demo', 'market_v0', 'production'], help='Run mode (default: demo)')
    
    args = parser.parse_args()

    # Always define today (used in prints + logs)
    today = date.today()
    
    # If date provided, use it
    if args.date:
        run_date = date.fromisoformat(args.date)
    else:
        # Default to previous Friday (for Monday morning run)
        run_date = get_previous_friday(today)
    
    print(f"{'#'*80}")
    print(f"WAKE ROBIN PRODUCTION RUN - {run_date.isoformat()}")
    print(f"MODE: {args.mode.upper()}")
    print(f"{'#'*80}")
    print(f"  Today: {today.isoformat()}")
    print(f"  Run Date: {run_date.isoformat()} (previous Friday)")
    print()
    
    # Back-compat alias: "production" == "market_v0"
    mode = 'market_v0' if args.mode == 'production' else args.mode
    
    # Import and run pipeline
    sys.path.append('src')
    from run_pipeline import run_pipeline
    
    success = run_pipeline(as_of_date=run_date, verify=False, mode=mode)
    
    if success:
        print(f"{'#'*80}")
        print("PRODUCTION RUN COMPLETED SUCCESSFULLY")
        print(f"{'#'*80}")
        return 0
    else:
        print(f"{'#'*80}")
        print("PRODUCTION RUN FAILED")
        print(f"{'#'*80}")
        return 1

if __name__ == "__main__":
    sys.exit(main())