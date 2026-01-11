"""FDA/Regulatory calendar client (networking allowed ONLY here).

Supports:
- Loading from local CSV files (data/regulatory/)
- Future: FDA calendar API integration

Event types:
- PDUFA: Prescription Drug User Fee Act action date
- ADCOMM: Advisory Committee meeting
- SUBMISSION: NDA/BLA submission
- APPROVAL: Drug approval
- CRL: Complete Response Letter
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd


class FDACalendarClient:
    """FDA regulatory calendar client.

    Production implementation loads from local CSV files.
    For live API integration, extend this class.
    """

    def __init__(self, data_dir: Path = Path("data/regulatory")):
        self.data_dir = data_dir

    def fetch_events(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Fetch regulatory events for tickers in universe.

        Looks for files matching: data/regulatory/fda_calendar_{YYYY}.csv
        Expected columns: ticker, event_type, event_date, status, event_description
        """
        tickers = set(str(t).upper().strip() for t in universe_df["ticker"].tolist())

        # Try to load from yearly calendar files
        events = self._load_from_files(as_of, tickers)

        if events.empty:
            # Return empty DataFrame with correct schema
            return pd.DataFrame(columns=[
                "ticker", "event_type", "event_date", "status", "event_description"
            ])

        return events

    def _load_from_files(self, as_of: date, tickers: set) -> pd.DataFrame:
        """Load events from local CSV files."""
        all_events: List[Dict[str, Any]] = []

        # Look for calendar files for current and next year
        years_to_check = [as_of.year, as_of.year + 1]

        for year in years_to_check:
            calendar_file = self.data_dir / f"fda_calendar_{year}.csv"
            if calendar_file.exists():
                df = pd.read_csv(calendar_file)
                df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()

                # Filter to universe tickers and future events
                df = df[df["ticker"].isin(tickers)]
                if "event_date" in df.columns:
                    df["event_date"] = pd.to_datetime(df["event_date"]).dt.date
                    df = df[df["event_date"] >= as_of]

                for _, row in df.iterrows():
                    all_events.append({
                        "ticker": row.get("ticker", ""),
                        "event_type": row.get("event_type", "OTHER"),
                        "event_date": row.get("event_date", "").isoformat() if hasattr(row.get("event_date", ""), "isoformat") else str(row.get("event_date", "")),
                        "status": row.get("status", "scheduled"),
                        "event_description": row.get("event_description", ""),
                    })

        return pd.DataFrame(all_events)


@dataclass(frozen=True)
class DemoFDACalendarClient(FDACalendarClient):
    """Offline demo client with sample regulatory events."""

    def fetch_events(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Return sample regulatory events for demo/testing."""
        rows = []

        # Generate sample events for known biotech tickers
        sample_events = {
            "MRNA": [
                {"event_type": "PDUFA", "event_date": "2024-06-15", "status": "scheduled", "event_description": "RSV vaccine NDA decision"},
            ],
            "GILD": [
                {"event_type": "ADCOMM", "event_date": "2024-04-20", "status": "scheduled", "event_description": "Advisory committee for lenacapavir"},
            ],
            "VRTX": [
                {"event_type": "PDUFA", "event_date": "2024-08-30", "status": "scheduled", "event_description": "Casgevy sickle cell approval"},
            ],
            "REGN": [
                {"event_type": "SUBMISSION", "event_date": "2024-03-01", "status": "filed", "event_description": "Dupixent COPD sBLA"},
            ],
            "BIIB": [
                {"event_type": "PDUFA", "event_date": "2024-07-24", "status": "scheduled", "event_description": "Lecanemab traditional approval"},
            ],
        }

        for _, r in universe_df.iterrows():
            ticker = str(r["ticker"]).upper().strip()
            if ticker in sample_events:
                for event in sample_events[ticker]:
                    rows.append({
                        "ticker": ticker,
                        "event_type": event["event_type"],
                        "event_date": event["event_date"],
                        "status": event["status"],
                        "event_description": event["event_description"],
                    })

        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
            "ticker", "event_type", "event_date", "status", "event_description"
        ])
