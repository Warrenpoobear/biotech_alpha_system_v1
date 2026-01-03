"""CLI: build fixtures for an as_of date.

This is the ONLY path that can touch network clients (if you disable demo mode).
"""

from __future__ import annotations
import argparse
from datetime import date
from pathlib import Path
import pandas as pd

from src.data.fixtures_builder import FixturesBuilder

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True, type=date.fromisoformat)
    ap.add_argument("--fixtures", default="fixtures")
    ap.add_argument("--universe-fixture", default=None, help="Path to universe CSV/Parquet; default uses fixtures/asof=.../universe")
    ap.add_argument("--demo", action="store_true", help="Use offline demo clients (default)")
    ap.add_argument("--live", action="store_true", help="Use live clients for ALL sources (requires implementing all real clients)")
    ap.add_argument("--live-ct", action="store_true", help="Use live ClinicalTrials.gov, but keep demo FDA/SEC/pricing")
    args = ap.parse_args()

    if args.live and args.live_ct:
        raise SystemExit("Choose only one: --live or --live-ct")

    fixtures_base = Path(args.fixtures)
    ub = args.universe_fixture
    if ub:
        p = Path(ub)
        if p.suffix == ".parquet":
            universe = pd.read_parquet(p)
        else:
            universe = pd.read_csv(p)
    else:
        # Default: load existing universe fixture for as_of
        u = fixtures_base / f"asof={args.as_of.isoformat()}" / "universe.csv"
        universe = pd.read_csv(u)

    builder = FixturesBuilder(
        fixtures_base=fixtures_base,
        use_demo_clients=(not args.live),
        live_clinicaltrials=bool(args.live_ct),
    )
    refs = builder.build_fixtures_for_date(args.as_of, universe)
    print("Built fixtures:", refs)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
