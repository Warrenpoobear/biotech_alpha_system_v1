"""Agent 1: Science & Catalyst Map (fixture-driven, deterministic).

Reads:
  - clinical_trials fixture
  - regulatory fixture

Produces:
  - SciencePacket per ticker
  - suppression flags if fixture columns are missing

NOTE: This is intentionally conservative and fail-loud: if no trial rows exist, the packet is
still produced but includes suppression.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from src.determinism.run_id import RunConfig
from src.determinism.fixtures import FixtureManager
from src.determinism.hashing import deterministic_hash
from src.schemas.common import PacketMeta, ProvenanceRef, SuppressionFlag
from src.schemas.science_packet import SciencePacket, TrialPhase, Catalyst, CatalystType

def _utc_stamp() -> str:
    # For PIT runs, this may be omitted; but when present it must be stable.
    # v1 uses a fixed stamp derived from as_of to avoid nondeterminism.
    return "PIT"

def _parse_date(x) -> Optional[date]:
    if x is None or (isinstance(x, float) and pd.isna(x)) or (isinstance(x, str) and not x.strip()):
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    # handle ISO string
    try:
        return date.fromisoformat(str(x)[:10])
    except Exception:
        return None

def _phase_from_str(s: str) -> TrialPhase:
    s = (s or "").strip().lower()
    if "phase3" in s or s == "3":
        return TrialPhase.phase3
    if "phase2" in s or s == "2":
        return TrialPhase.phase2
    if "phase1" in s or s == "1":
        return TrialPhase.phase1
    if "pivotal" in s:
        return TrialPhase.pivotal
    if "phase4" in s or s == "4":
        return TrialPhase.phase4
    return TrialPhase.unknown

def _load_design_quality_weights(path: Path) -> Dict[str, Any]:
    """Load design quality weights from external config file."""
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    # Fallback defaults if config file missing
    return {
        "trial_design": {"randomized": 0.20, "controlled": 0.20, "blinded": 0.15, "powered": 0.15},
        "endpoint": {"overall_survival": 0.30, "progression_free": 0.20, "objective_response": 0.10}
    }


@dataclass(frozen=True)
class ScienceCatalystAgent:
    cfg: RunConfig
    fixtures_base: Path
    dq_weights_path: Path = Path("config/design_quality_weights.yaml")

    def run(self, tickers: List[str]) -> Dict[str, SciencePacket]:
        fm = FixtureManager(self.fixtures_base)
        trials = fm.load_df(self.cfg.as_of, "clinical_trials")
        reg = fm.load_df(self.cfg.as_of, "regulatory")
        dq_weights = _load_design_quality_weights(self.dq_weights_path)

        out: Dict[str, SciencePacket] = {}
        for t in sorted(tickers):
            out[t] = self._packet_for_ticker(t, trials, reg, dq_weights)
        return out

    def _packet_for_ticker(self, ticker: str, trials: pd.DataFrame, reg: pd.DataFrame, dq_weights: Dict[str, Any]) -> SciencePacket:
        tt = trials[trials["ticker"].astype(str).str.upper().str.strip() == ticker].copy()
        rr = reg[reg["ticker"].astype(str).str.upper().str.strip() == ticker].copy()

        suppression: List[str] = []
        prov: List[ProvenanceRef] = [
            ProvenanceRef(source="fixture", uri=f"fixtures/asof={self.cfg.as_of.isoformat()}/clinical_trials"),
            ProvenanceRef(source="fixture", uri=f"fixtures/asof={self.cfg.as_of.isoformat()}/regulatory"),
        ]

        # Minimal extraction: use first trial row as primary
        if len(tt) == 0:
            suppression.append("no_trial_rows")
            trial_id = "NCT00000000"
            phase = TrialPhase.unknown
        else:
            tt = tt.sort_values(by=["nct_id"], kind="mergesort")
            trial_id = str(tt.iloc[0]["nct_id"])
            phase = _phase_from_str(str(tt.iloc[0].get("phase", "")))

        # optional columns
        drug_name = "UNKNOWN"
        indication = "UNKNOWN"
        primary_endpoint = "UNKNOWN"
        for col, flag, default in [
            ("drug_name", "missing_drug_name", "UNKNOWN"),
            ("indication", "missing_indication", "UNKNOWN"),
            ("primary_endpoint", "missing_primary_endpoint", "UNKNOWN"),
        ]:
            if col in tt.columns and len(tt) > 0 and str(tt.iloc[0].get(col, "")).strip():
                if col == "drug_name":
                    drug_name = str(tt.iloc[0][col])
                elif col == "indication":
                    indication = str(tt.iloc[0][col])
                elif col == "primary_endpoint":
                    primary_endpoint = str(tt.iloc[0][col])
            else:
                suppression.append(flag)

        # Design quality score heuristic (0-1); optional booleans if present
        dq = 0.0
        def bcol(name: str) -> Optional[bool]:
            if len(tt) == 0 or name not in tt.columns:
                return None
            v = tt.iloc[0].get(name, None)
            if pd.isna(v):
                return None
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            if s in ("true","1","yes","y"):
                return True
            if s in ("false","0","no","n"):
                return False
            return None

        is_randomized = bcol("is_randomized") or False
        is_controlled = bcol("is_controlled") or False
        is_blinded = bcol("is_blinded") or False
        is_powered = bcol("is_powered") or False

        # Load weights from config (externalized for tuning)
        td_weights = dq_weights.get("trial_design", {})
        ep_weights = dq_weights.get("endpoint", {})

        # Score components using configurable weights
        dq += td_weights.get("randomized", 0.20) if is_randomized else 0.0
        dq += td_weights.get("controlled", 0.20) if is_controlled else 0.0
        dq += td_weights.get("blinded", 0.15) if is_blinded else 0.0
        dq += td_weights.get("powered", 0.15) if is_powered else 0.0

        ep = (primary_endpoint or "").lower()
        if "overall survival" in ep or ep.strip() == "os":
            dq += ep_weights.get("overall_survival", 0.30)
        elif "pfs" in ep or "progression" in ep:
            dq += ep_weights.get("progression_free", 0.20)
        elif "orr" in ep or "response" in ep:
            dq += ep_weights.get("objective_response", 0.10)

        dq = max(0.0, min(1.0, dq))
        extraction_confidence = 0.5
        if len(suppression) <= 1:
            extraction_confidence = 0.8

        # Catalysts
        cats: List[Catalyst] = []

        # clinical trials completion_date -> topline_results
        if "completion_date" in tt.columns and len(tt) > 0:
            for _, row in tt.iterrows():
                d = _parse_date(row.get("completion_date", None))
                if d:
                    cats.append(Catalyst(
                        type=CatalystType.topline_results,
                        date=d,
                        description=f"{row.get('phase','')} completion/topline ({row.get('nct_id','')})",
                        impact_tier=2 if "3" in str(row.get("phase","")) else 3,
                        source="clinical_trials",
                        source_uri=None,
                    ))
        else:
            suppression.append("missing_completion_date")

        # regulatory event_date
        if "event_date" in rr.columns and len(rr) > 0:
            rr = rr.sort_values(by=["event_date"], kind="mergesort")
            for _, row in rr.iterrows():
                d = _parse_date(row.get("event_date", None))
                if not d:
                    continue
                et = str(row.get("event_type", "")).upper()
                ctype = CatalystType.other
                if "PDUFA" in et:
                    ctype = CatalystType.pdufa_date
                elif "ADCOM" in et or "ADCOMM" in et:
                    ctype = CatalystType.adcomm_meeting
                elif "SUBMISSION" in et or "FILING" in et:
                    ctype = CatalystType.regulatory_submission
                cats.append(Catalyst(
                    type=ctype,
                    date=d,
                    description=f"{row.get('event_type','')} ({row.get('status','')})",
                    impact_tier=1 if ctype == CatalystType.pdufa_date else 2,
                    source="regulatory",
                    source_uri=None,
                ))
        else:
            suppression.append("missing_regulatory_event_date")

        # next catalyst
        future = [c for c in cats if c.date and (c.date >= self.cfg.as_of)]
        future = sorted(future, key=lambda c: (c.date.isoformat(), c.type.value, c.description))
        next_cat = future[0] if future else None

        horizon = None
        if next_cat and next_cat.date:
            horizon = (next_cat.date - self.cfg.as_of).days

        # deterministic packet_id
        packet_id = f"science_{deterministic_hash({'ticker': ticker, 'as_of': self.cfg.as_of.isoformat()})}"

        meta = PacketMeta(
            packet_type="science",
            run_id=self.cfg.to_run_id(),
            as_of=self.cfg.as_of.isoformat(),
            generator="agent1_science_catalyst",
            code_version=self.cfg.code_version,
            provenance=prov,
            suppression=[SuppressionFlag(code=s, severity="warn", reason=s) for s in sorted(set(suppression))],
        )

        pkt = SciencePacket(
            meta=meta,
            packet_id=packet_id,
            as_of=self.cfg.as_of,
            extraction_timestamp=_utc_stamp(),
            ticker=ticker,
            drug_name=drug_name,
            indication=indication,
            mechanism_of_action=None,
            trial_id=trial_id,
            phase=phase,
            enrollment_target=None,
            enrollment_actual=None,
            is_randomized=is_randomized,
            is_controlled=is_controlled,
            is_blinded=is_blinded,
            is_powered=is_powered,
            primary_endpoint=primary_endpoint,
            statistical_plan=None,
            catalysts=sorted(cats, key=lambda c: ((c.date.isoformat() if c.date else "9999-99-99"), c.type.value, c.description)),
            next_catalyst=next_cat,
            catalyst_horizon_days=horizon,
            source_urls=[p.uri for p in prov],
            extraction_confidence=extraction_confidence,
            suppression_flags=sorted(set(suppression)),
            data_quality_score=dq,
            provenance=prov,
            suppression=[SuppressionFlag(code=s, severity="warn", reason=s) for s in sorted(set(suppression))],
        )
        return pkt
