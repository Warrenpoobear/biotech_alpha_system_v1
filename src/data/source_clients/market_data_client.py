"""Market pricing data client (networking allowed ONLY here).

Supports:
- Loading from local CSV files (data/market/)
- Future: Yahoo Finance, Polygon.io, or other market data API integration

Data fields:
- ticker: Stock ticker symbol
- date: Price date (ISO format)
- close: Closing price
- volume: Daily trading volume
- shares_outstanding: Total shares outstanding
- market_cap: Market capitalization (close * shares_outstanding)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd


class MarketDataClient:
    """Market data client.

    Production implementation loads from local CSV files.
    For live API integration (Yahoo Finance, Polygon, etc.), extend this class.
    """

    def __init__(self, data_dir: Path = Path("data/market")):
        self.data_dir = data_dir

    def fetch_pricing(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Fetch pricing data for tickers in universe.

        Looks for files matching: data/market/pricing_{YYYY-MM-DD}.csv or pricing_latest.csv
        Expected columns: ticker, date, close, volume, shares_outstanding
        """
        tickers = set(str(t).upper().strip() for t in universe_df["ticker"].tolist())

        # Try to load from date-specific or latest file
        pricing = self._load_from_files(as_of, tickers)

        if pricing.empty:
            # Return empty DataFrame with correct schema
            return pd.DataFrame(columns=[
                "ticker", "date", "close", "volume", "shares_outstanding", "market_cap"
            ])

        return pricing

    def _load_from_files(self, as_of: date, tickers: set) -> pd.DataFrame:
        """Load pricing data from local CSV files."""
        all_rows: List[Dict[str, Any]] = []

        # Look for date-specific file first, then latest
        date_file = self.data_dir / f"pricing_{as_of.isoformat()}.csv"
        latest_file = self.data_dir / "pricing_latest.csv"

        target_file = date_file if date_file.exists() else latest_file

        if target_file.exists():
            df = pd.read_csv(target_file)
            df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()

            # Filter to universe tickers
            df = df[df["ticker"].isin(tickers)]

            for _, row in df.iterrows():
                close = self._safe_float(row.get("close"))
                volume = self._safe_float(row.get("volume"))
                shares = self._safe_float(row.get("shares_outstanding"))
                market_cap = (close * shares) if (close and shares) else None

                all_rows.append({
                    "ticker": row.get("ticker", ""),
                    "date": row.get("date", as_of.isoformat()),
                    "close": close,
                    "volume": volume,
                    "shares_outstanding": shares,
                    "market_cap": market_cap,
                })

        return pd.DataFrame(all_rows)

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Safely convert value to float."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


@dataclass(frozen=True)
class DemoMarketDataClient(MarketDataClient):
    """Offline demo client with sample pricing data."""

    def fetch_pricing(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Return sample pricing data for demo/testing."""
        rows = []

        # Sample pricing data for major biotech tickers
        sample_data = {
            "MRNA": {"close": 98.50, "volume": 8_500_000, "shares_outstanding": 385_000_000},
            "GILD": {"close": 72.30, "volume": 6_200_000, "shares_outstanding": 1_250_000_000},
            "VRTX": {"close": 415.20, "volume": 1_100_000, "shares_outstanding": 255_000_000},
            "REGN": {"close": 890.40, "volume": 520_000, "shares_outstanding": 110_000_000},
            "BIIB": {"close": 215.80, "volume": 1_800_000, "shares_outstanding": 145_000_000},
            "AMGN": {"close": 278.90, "volume": 2_400_000, "shares_outstanding": 535_000_000},
            "ALNY": {"close": 185.50, "volume": 950_000, "shares_outstanding": 125_000_000},
            "BMRN": {"close": 82.40, "volume": 780_000, "shares_outstanding": 195_000_000},
            "SGEN": {"close": 205.10, "volume": 1_200_000, "shares_outstanding": 185_000_000},
            "INCY": {"close": 58.90, "volume": 2_100_000, "shares_outstanding": 220_000_000},
        }

        for _, r in universe_df.iterrows():
            ticker = str(r["ticker"]).upper().strip()
            if ticker in sample_data:
                data = sample_data[ticker]
                close = data["close"]
                shares = data["shares_outstanding"]
                rows.append({
                    "ticker": ticker,
                    "date": as_of.isoformat(),
                    "close": close,
                    "volume": data["volume"],
                    "shares_outstanding": shares,
                    "market_cap": close * shares,
                })
            else:
                # Generate plausible default data for unknown tickers
                rows.append({
                    "ticker": ticker,
                    "date": as_of.isoformat(),
                    "close": 50.0,
                    "volume": 500_000,
                    "shares_outstanding": 100_000_000,
                    "market_cap": 5_000_000_000,
                })

        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
            "ticker", "date", "close", "volume", "shares_outstanding", "market_cap"
        ])
