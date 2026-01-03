"""FDA/Regulatory calendar client (networking allowed ONLY here).

v1: interface stub + offline demo client.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import pandas as pd

class FDACalendarClient:
    def fetch_events(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError("Implement FDA calendar retrieval in your environment (fixtures_builder only).")

@dataclass(frozen=True)
class DemoFDACalendarClient(FDACalendarClient):
    def fetch_events(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, r in universe_df.iterrows():
            t = str(r["ticker"]).upper().strip()
            if t == "AAA":
                rows.append({"ticker": "AAA", "event_type": "PDUFA", "event_date": "2024-12-15", "status": "planned", "event_description": "DrugX NDA"})
        return pd.DataFrame(rows)
