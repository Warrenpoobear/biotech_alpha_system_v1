"""SEC EDGAR client (networking allowed ONLY here).

v1: interface stub + offline demo client.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import pandas as pd

class SECEdgarClient:
    def fetch_filings(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError("Implement EDGAR/13F retrieval in your environment (fixtures_builder only).")

@dataclass(frozen=True)
class DemoSECEdgarClient(SECEdgarClient):
    def fetch_filings(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        # Placeholder minimal table (extend later)
        return pd.DataFrame([{"as_of": as_of.isoformat(), "note": "demo"}])
