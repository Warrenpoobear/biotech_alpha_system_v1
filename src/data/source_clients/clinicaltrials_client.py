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
    conditions = protocol.get("conditionsModule", {}) or {}
    interventions = protocol.get("armsInterventionsModule", {}) or {}
    outcomes = protocol.get("outcomesModule", {}) or {}

    nct_id = ident.get("nctId") or study.get("nctId")
    if not nct_id:
        return None

    # Prefer primary completion date; fallback to completion date.
    pc = status.get("primaryCompletionDateStruct") or {}
    cc = status.get("completionDateStruct") or {}
    completion = _date_struct_to_iso(pc) or _date_struct_to_iso(cc)

    phase = (design.get("phase") or "unknown").lower().replace(" ", "")
    overall_status = status.get("overallStatus") or ""

    # Extract drug name from interventions (first DRUG type)
    drug_name = _extract_drug_name(interventions)

    # Extract primary indication from conditions
    indication = _extract_indication(conditions)

    # Extract primary endpoint from outcomes
    primary_endpoint = _extract_primary_endpoint(outcomes)

    # Determine blinding from design info
    masking = design.get("maskingInfo", {}) or {}
    is_blinded = _is_blinded(masking)

    # Determine if controlled (has comparator arm)
    is_controlled = _is_controlled(interventions, design)

    # Check if powered (enrollment target exists)
    enrollment = design.get("enrollmentInfo", {}) or {}
    is_powered = bool(enrollment.get("count") and int(enrollment.get("count", 0)) >= 50)

    return {
        "ticker": ticker,
        "nct_id": str(nct_id),
        "phase": str(phase),
        "status": str(overall_status),
        "completion_date": completion,
        "drug_name": drug_name,
        "indication": indication,
        "primary_endpoint": primary_endpoint,
        "is_randomized": (design.get("designAllocation") == "RANDOMIZED"),
        "is_controlled": is_controlled,
        "is_blinded": is_blinded,
        "is_powered": is_powered,
    }


def _extract_drug_name(interventions: Dict[str, Any]) -> str:
    """Extract first drug intervention name."""
    intervention_list = interventions.get("interventions", []) or []
    for intv in intervention_list:
        if intv.get("type", "").upper() in ("DRUG", "BIOLOGICAL"):
            return str(intv.get("name", "")).strip()
    # Fallback to first intervention of any type
    if intervention_list:
        return str(intervention_list[0].get("name", "")).strip()
    return ""


def _extract_indication(conditions: Dict[str, Any]) -> str:
    """Extract primary condition/indication."""
    condition_list = conditions.get("conditions", []) or []
    if condition_list:
        return str(condition_list[0]).strip()
    return ""


def _extract_primary_endpoint(outcomes: Dict[str, Any]) -> str:
    """Extract primary outcome measure."""
    primary = outcomes.get("primaryOutcomes", []) or []
    if primary:
        measure = primary[0].get("measure", "")
        return str(measure).strip()[:200]  # Truncate long descriptions
    return ""


def _is_blinded(masking: Dict[str, Any]) -> bool:
    """Determine if study is blinded from masking info."""
    masking_type = (masking.get("masking") or "").upper()
    if masking_type in ("DOUBLE", "TRIPLE", "QUADRUPLE"):
        return True
    who_masked = masking.get("whoMasked", []) or []
    # If participants or investigators are masked, consider it blinded
    return any(w.upper() in ("PARTICIPANT", "INVESTIGATOR") for w in who_masked)


def _is_controlled(interventions: Dict[str, Any], design: Dict[str, Any]) -> bool:
    """Determine if study has a control arm."""
    # Check for placebo or control in interventions
    intervention_list = interventions.get("interventions", []) or []
    for intv in intervention_list:
        name = (intv.get("name") or "").lower()
        if "placebo" in name or "control" in name or "standard of care" in name:
            return True
    # Check arm groups for control
    arms = interventions.get("armGroups", []) or []
    for arm in arms:
        arm_type = (arm.get("type") or "").upper()
        if arm_type in ("PLACEBO_COMPARATOR", "ACTIVE_COMPARATOR", "NO_INTERVENTION"):
            return True
    return False


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
    """Offline demo client with realistic biotech trial data."""

    # Sample trial data for major biotech tickers
    SAMPLE_TRIALS: Dict[str, List[Dict[str, Any]]] = {
        "MRNA": [
            {"nct_id": "NCT04470427", "phase": "phase3", "status": "Active, not recruiting",
             "completion_date": "2024-12-01", "drug_name": "mRNA-1273",
             "indication": "COVID-19", "primary_endpoint": "Vaccine efficacy",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
            {"nct_id": "NCT05127434", "phase": "phase2", "status": "Recruiting",
             "completion_date": "2025-06-01", "drug_name": "mRNA-4157",
             "indication": "Melanoma", "primary_endpoint": "Recurrence-free survival",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
        ],
        "GILD": [
            {"nct_id": "NCT04280705", "phase": "phase3", "status": "Completed",
             "completion_date": "2023-03-01", "drug_name": "Remdesivir",
             "indication": "COVID-19", "primary_endpoint": "Time to recovery",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
            {"nct_id": "NCT04501952", "phase": "phase2", "status": "Recruiting",
             "completion_date": "2025-01-01", "drug_name": "Lenacapavir",
             "indication": "HIV-1 infection", "primary_endpoint": "Viral suppression",
             "is_randomized": True, "is_controlled": True, "is_blinded": False, "is_powered": True},
        ],
        "VRTX": [
            {"nct_id": "NCT04046315", "phase": "phase3", "status": "Active, not recruiting",
             "completion_date": "2024-09-01", "drug_name": "VX-548",
             "indication": "Acute pain", "primary_endpoint": "Pain intensity difference",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
        ],
        "REGN": [
            {"nct_id": "NCT04381936", "phase": "phase3", "status": "Completed",
             "completion_date": "2022-06-01", "drug_name": "REGEN-COV",
             "indication": "COVID-19", "primary_endpoint": "Hospitalization or death",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
            {"nct_id": "NCT03985293", "phase": "phase3", "status": "Active, not recruiting",
             "completion_date": "2024-12-01", "drug_name": "Dupixent",
             "indication": "Atopic dermatitis", "primary_endpoint": "EASI-75 response",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
        ],
        "BIIB": [
            {"nct_id": "NCT03887455", "phase": "phase3", "status": "Active, not recruiting",
             "completion_date": "2024-10-01", "drug_name": "Lecanemab",
             "indication": "Alzheimer's disease", "primary_endpoint": "CDR-SB change",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
        ],
        "ALNY": [
            {"nct_id": "NCT04153149", "phase": "phase3", "status": "Recruiting",
             "completion_date": "2025-03-01", "drug_name": "Patisiran",
             "indication": "hATTR amyloidosis", "primary_endpoint": "mNIS+7 change",
             "is_randomized": True, "is_controlled": True, "is_blinded": True, "is_powered": True},
        ],
        "BMRN": [
            {"nct_id": "NCT03173144", "phase": "phase3", "status": "Active, not recruiting",
             "completion_date": "2024-08-01", "drug_name": "Valoctocogene roxaparvovec",
             "indication": "Hemophilia A", "primary_endpoint": "Factor VIII activity",
             "is_randomized": False, "is_controlled": False, "is_blinded": False, "is_powered": True},
        ],
        "INCY": [
            {"nct_id": "NCT04551066", "phase": "phase2", "status": "Recruiting",
             "completion_date": "2025-06-01", "drug_name": "Parsaclisib",
             "indication": "Follicular lymphoma", "primary_endpoint": "Objective response rate",
             "is_randomized": True, "is_controlled": True, "is_blinded": False, "is_powered": True},
        ],
    }

    def fetch_trials(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Return sample trial data for demo/testing."""
        rows = []
        for _, r in universe_df.iterrows():
            ticker = str(r["ticker"]).upper().strip()
            if ticker in self.SAMPLE_TRIALS:
                for trial in self.SAMPLE_TRIALS[ticker]:
                    rows.append({"ticker": ticker, **trial})
            else:
                # Generate placeholder trial for unknown tickers
                rows.append({
                    "ticker": ticker,
                    "nct_id": f"NCT{hash(ticker) % 100000000:08d}",
                    "phase": "phase2",
                    "status": "Recruiting",
                    "completion_date": "2025-06-01",
                    "drug_name": f"{ticker}-001",
                    "indication": "Oncology",
                    "primary_endpoint": "Overall response rate",
                    "is_randomized": True,
                    "is_controlled": True,
                    "is_blinded": False,
                    "is_powered": True,
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["ticker", "nct_id"], kind="mergesort").reset_index(drop=True)
        return df
