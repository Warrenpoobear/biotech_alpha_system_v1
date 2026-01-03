"""ClinicalTrials.gov client (networking allowed ONLY here).

This file intentionally provides:
- an interface contract
- a deterministic normalization surface

For v1 offline operation, use `DemoClinicalTrialsClient` (no network).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any, List
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd

class ClinicalTrialsAPIError(RuntimeError):
    pass


class ClinicalTrialsGovV2Client:
    """ClinicalTrials.gov API v2 client (networking allowed ONLY from fixtures_builder)."""

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(self, *, timeout_s: int = 30, max_retries: int = 3, rps: float = 5.0):
        self.timeout_s = timeout_s
        self.min_delay_s = 1.0 / max(rps, 0.1)
        self._last_req = 0.0

        sess = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        sess.mount("https://", HTTPAdapter(max_retries=retry))
        self.session = sess

        ua = os.getenv("CTGOV_USER_AGENT", "BiotechAlphaSystem/1.0 (fixtures_builder)")
        self.headers = {"User-Agent": ua, "Accept": "application/json"}

    def _rate_limit(self) -> None:
        now = time.time()
        delta = now - self._last_req
        if delta < self.min_delay_s:
            time.sleep(self.min_delay_s - delta)
        self._last_req = time.time()

    def fetch_studies_for_sponsor(self, sponsor_name: str, *, phases: List[str], page_size: int = 100) -> List[Dict[str, Any]]:
        """Return raw studies JSON objects for a sponsor."""
        sponsor = sponsor_name.strip()
        if not sponsor:
            return []

        # CT.gov advanced query syntax (v2): use AREA[...] clauses.
        sponsor_query = f'AREA[LeadSponsorName]"{sponsor}" OR AREA[SponsorName]"{sponsor}"'
        phase_filter = f'AREA[Phase]{" OR ".join(phases)}' if phases else ""

        fields = [
            "NCTId",
            "Phase",
            "StatusModule",
            "DesignModule",
            "ConditionsModule",
            "InterventionsModule",
            "IdentificationModule",
            "SponsorModule",
        ]

        studies: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            self._rate_limit()
            params: Dict[str, Any] = {
                "query.term": sponsor_query,
                "pageSize": int(page_size),
                "fields": ",".join(fields),
            }
            if phase_filter:
                params["filter.advanced"] = phase_filter
            if page_token:
                params["pageToken"] = page_token

            resp = self.session.get(self.BASE_URL, params=params, headers=self.headers, timeout=self.timeout_s)
            if resp.status_code >= 400:
                raise ClinicalTrialsAPIError(f"CT.gov HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            batch = data.get("studies", []) or []
            studies.extend(batch)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return studies


class ClinicalTrialsClient:
    """Live client. Networking is allowed ONLY from fixtures_builder."""

    def __init__(self, *, timeout_s: int = 30, max_retries: int = 3, rps: float = 5.0):
        self._api = ClinicalTrialsGovV2Client(timeout_s=timeout_s, max_retries=max_retries, rps=rps)

    def fetch_trials(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Fetch and normalize trials for the provided universe.

        Determinism note: live API calls are *not* deterministic across time.
        Determinism contract applies AFTER fixtures are frozen.
        """
        phases = ["Phase 1", "Phase 2", "Phase 3"]
        rows: List[Dict[str, Any]] = []

        for _, r in universe_df.iterrows():
            ticker = str(r.get("ticker", "")).upper().strip()
            sponsor = str(r.get("name", "")).strip()
            if not ticker or not sponsor:
                continue

            studies = self._api.fetch_studies_for_sponsor(sponsor, phases=phases)
            for s in studies:
                rec = _normalize_study_minimal(s, ticker=ticker)
                if rec:
                    rows.append(rec)

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["ticker", "nct_id"], kind="mergesort").reset_index(drop=True)
        return df


def _normalize_study_minimal(study: Dict[str, Any], *, ticker: str) -> Optional[Dict[str, Any]]:
    """Normalize CT.gov v2 study JSON to the *minimum* schema needed by Agent 1."""
    protocol = study.get("protocolSection", {}) or {}
    ident = protocol.get("identificationModule", {}) or {}
    status = protocol.get("statusModule", {}) or {}
    design = protocol.get("designModule", {}) or {}

    nct_id = ident.get("nctId") or study.get("nctId")
    if not nct_id:
        return None

    # Prefer primary completion date; fallback to completion date.
    pc = status.get("primaryCompletionDateStruct") or {}
    cc = status.get("completionDateStruct") or {}
    completion = _date_struct_to_iso(pc) or _date_struct_to_iso(cc)

    phase = (design.get("phase") or "unknown").lower().replace(" ", "")
    overall_status = status.get("overallStatus") or ""

    # Minimal deterministic record.
    return {
        "ticker": ticker,
        "nct_id": str(nct_id),
        "phase": str(phase),
        "status": str(overall_status),
        "completion_date": completion,
        # Optional fields (Agent 1 will default if missing)
        "drug_name": "",
        "indication": "",
        "primary_endpoint": "",
        "is_randomized": (design.get("designAllocation") == "RANDOMIZED"),
        "is_controlled": False,
        "is_blinded": False,
        "is_powered": False,
    }


def _date_struct_to_iso(ds: Dict[str, Any]) -> Optional[str]:
    try:
        y = ds.get("year")
        if not y:
            return None
        m = int(ds.get("month") or 1)
        d = int(ds.get("day") or 1)
        return date(int(y), m, d).isoformat()
    except Exception:
        return None

@dataclass(frozen=True)
class DemoClinicalTrialsClient(ClinicalTrialsClient):
    """Offline demo client (deterministic sample data)."""
    def fetch_trials(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, r in universe_df.iterrows():
            t = str(r["ticker"]).upper().strip()
            rows.append({
                "ticker": t,
                "nct_id": "NCT12345678" if t == "AAA" else "NCT87654321",
                "phase": "phase2" if t == "AAA" else "phase1",
                "status": "Recruiting",
                "completion_date": "2024-06-01" if t == "AAA" else "2024-09-01",
                "drug_name": "DrugX" if t == "AAA" else "DrugY",
                "indication": "oncology",
                "primary_endpoint": "PFS",
                "is_randomized": True if t == "AAA" else False,
                "is_controlled": True if t == "AAA" else False,
                "is_blinded": False,
                "is_powered": False,
            })
        return pd.DataFrame(rows)
