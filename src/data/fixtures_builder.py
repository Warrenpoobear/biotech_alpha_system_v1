"""Fixtures builder (the ONLY place networking is allowed).

Responsibilities:
  1) pull from live sources (or demo clients) at an as_of date
  2) normalize to canonical schemas
  3) write immutable fixtures + checksums under fixtures/asof=YYYY-MM-DD/
  4) emit a deterministic build manifest for audit

Production agents MUST read fixtures only.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from src.determinism.fixtures import FixtureManager
from src.determinism.hashing import deterministic_hash
from src.output.io import write_json

from src.data.source_clients.clinicaltrials_client import ClinicalTrialsClient, DemoClinicalTrialsClient
from src.data.source_clients.fda_calendar_client import FDACalendarClient, DemoFDACalendarClient
from src.data.source_clients.sec_edgar_client import SECEdgarClient, DemoSECEdgarClient
from src.data.source_clients.market_data_client import MarketDataClient, DemoMarketDataClient

@dataclass(frozen=True)
class FixturesBuilder:
    fixtures_base: Path = Path("fixtures")
    use_demo_clients: bool = True
    live_clinicaltrials: bool = False

    def _clients(self) -> Tuple[ClinicalTrialsClient, FDACalendarClient, SECEdgarClient, MarketDataClient]:
        if self.use_demo_clients:
            # Use live ClinicalTrials client if configured, otherwise demo
            ct = ClinicalTrialsClient() if self.live_clinicaltrials else DemoClinicalTrialsClient()
            return ct, DemoFDACalendarClient(), DemoSECEdgarClient(), DemoMarketDataClient()
        # Production mode - all live clients
        return ClinicalTrialsClient(), FDACalendarClient(), SECEdgarClient(), MarketDataClient()

    def build_fixtures_for_date(self, as_of: date, universe_df: pd.DataFrame) -> Dict[str, str]:
        """Build fixtures and return dict of {source: sha256}."""
        fm = FixtureManager(self.fixtures_base)
        ct, fda, sec, mkt = self._clients()

        # 1) fetch
        trials_raw = ct.fetch_trials(as_of=as_of, universe_df=universe_df)
        reg_raw = fda.fetch_events(as_of=as_of, universe_df=universe_df)
        pricing_raw = mkt.fetch_pricing(as_of=as_of, universe_df=universe_df)
        sec_raw = sec.fetch_filings(as_of=as_of, universe_df=universe_df)

        # 2) normalize (canonical column set)
        trials = self._normalize_trials(trials_raw)
        reg = self._normalize_regulatory(reg_raw)
        pricing = self._normalize_pricing(pricing_raw)
        sec_filings = self._normalize_sec_filings(sec_raw)

        # 3) write fixtures (csv by default for portability)
        refs = {}
        ref_trials = fm.create_df_fixture(trials, as_of, "clinical_trials", fmt="csv")
        refs["clinical_trials"] = ref_trials.sha256
        ref_reg = fm.create_df_fixture(reg, as_of, "regulatory", fmt="csv")
        refs["regulatory"] = ref_reg.sha256
        ref_pricing = fm.create_df_fixture(pricing, as_of, "pricing", fmt="csv")
        refs["pricing"] = ref_pricing.sha256
        ref_sec = fm.create_df_fixture(sec_filings, as_of, "sec_filings", fmt="csv")
        refs["sec_filings"] = ref_sec.sha256

        # 4) deterministic build manifest
        manifest = {
            "as_of": as_of.isoformat(),
            "fixtures_version": "v1",
            "use_demo_clients": self.use_demo_clients,
            "inputs_universe_hash": deterministic_hash({"rows": int(len(universe_df)), "tickers": sorted({str(t).upper().strip() for t in universe_df["ticker"].tolist()})}),
            "outputs": {k: v for k, v in sorted(refs.items())},
        }
        out_dir = self.fixtures_base / f"asof={as_of.isoformat()}"
        write_json(out_dir / "fixtures_build_manifest.json", manifest)

        return refs

    @staticmethod
    def _normalize_trials(df: pd.DataFrame) -> pd.DataFrame:
        # Ensure required columns exist; missing => empty/default
        cols = [
            "ticker","nct_id","phase","status","completion_date",
            "drug_name","indication","primary_endpoint",
            "is_randomized","is_controlled","is_blinded","is_powered",
        ]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        out = df[cols].copy()
        out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
        out["nct_id"] = out["nct_id"].astype(str).str.strip()
        out = out.sort_values(by=["ticker","nct_id"], kind="mergesort").reset_index(drop=True)
        return out

    @staticmethod
    def _normalize_regulatory(df: pd.DataFrame) -> pd.DataFrame:
        cols = ["ticker","event_type","event_date","status","event_description"]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        out = df[cols].copy()
        out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
        out = out.sort_values(by=["ticker","event_date","event_type"], kind="mergesort").reset_index(drop=True)
        return out

    @staticmethod
    def _normalize_pricing(df: pd.DataFrame) -> pd.DataFrame:
        cols = ["ticker", "close", "volume", "shares_outstanding"]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        out = df[cols].copy()
        out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
        out = out.sort_values(by=["ticker"], kind="mergesort").reset_index(drop=True)
        return out

    @staticmethod
    def _normalize_sec_filings(df: pd.DataFrame) -> pd.DataFrame:
        cols = ["ticker", "filing_type", "filing_date", "filer_name",
                "transaction_type", "shares", "value_usd", "description"]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        out = df[cols].copy()
        out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
        out = out.sort_values(by=["ticker", "filing_date", "filing_type"], kind="mergesort").reset_index(drop=True)
        return out
