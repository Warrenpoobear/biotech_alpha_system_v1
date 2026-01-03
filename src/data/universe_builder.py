"""Universe builder (v1).

v1 behavior:
- Loads `fixtures/asof=YYYY-MM-DD/universe.(parquet|csv|json)`
- Returns the tickers list deterministically (sorted, uppercase)
- No ETF ingestion yet (that belongs in fixtures_builder in a later phase)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List

import pandas as pd

from src.determinism.fixtures import FixtureManager

@dataclass(frozen=True)
class Universe:
    tickers: List[str]

class UniverseBuilder:
    def __init__(self, fixtures_base: Path):
        self.fixtures = FixtureManager(fixtures_base)

    def load_universe(self, as_of: date) -> Universe:
        df = self.fixtures.load_df(as_of, "universe")
        tickers = sorted({str(t).upper().strip() for t in df["ticker"].tolist() if str(t).strip()})
        return Universe(tickers=tickers)
