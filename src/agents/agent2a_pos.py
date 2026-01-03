"""Agent 2A: Probability of Success (PoS) — simple v1 model.

Inputs:
  - SciencePacket

Output:
  - PoSPacket

Notes:
  - Uses static base rates by phase & therapeutic area (TA proxy from indication string).
  - Applies deterministic adjustments for design quality and sponsor score.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List

from src.determinism.run_id import RunConfig
from src.determinism.hashing import deterministic_hash
from src.schemas.common import PacketMeta, ProvenanceRef, SuppressionFlag
from src.schemas.science_packet import SciencePacket, TrialPhase
from src.schemas.pos_packet import PoSPacket, PoSAdjustment

def _map_indication_to_ta(indication: str) -> str:
    s = (indication or "").lower()
    if any(k in s for k in ["tumor","cancer","oncolog","lymph","leuk","melanom"]):
        return "oncology"
    if any(k in s for k in ["neuro","alzheimer","parkinson","epilep","ms "]):
        return "neurology"
    if any(k in s for k in ["cardio","heart","stroke"]):
        return "cardio"
    if any(k in s for k in ["rare","orphan"]):
        return "rare_disease"
    if any(k in s for k in ["virus","infect","covid","hiv"]):
        return "infectious"
    return "other"

BASE_RATES = {
    "phase1": {"oncology": 0.45, "neurology": 0.50, "cardio": 0.55, "rare_disease": 0.60, "infectious": 0.65, "other": 0.50},
    "phase2": {"oncology": 0.25, "neurology": 0.30, "cardio": 0.35, "rare_disease": 0.40, "infectious": 0.45, "other": 0.30},
    "phase3": {"oncology": 0.50, "neurology": 0.55, "cardio": 0.60, "rare_disease": 0.65, "infectious": 0.70, "other": 0.55},
    "phase4": {"oncology": 0.70, "neurology": 0.75, "cardio": 0.80, "rare_disease": 0.80, "infectious": 0.85, "other": 0.75},
    "pivotal": {"oncology": 0.55, "neurology": 0.60, "cardio": 0.65, "rare_disease": 0.70, "infectious": 0.75, "other": 0.60},
    "unknown": {"oncology": 0.30, "neurology": 0.30, "cardio": 0.30, "rare_disease": 0.35, "infectious": 0.35, "other": 0.30},
}

def _phase_key(p: TrialPhase) -> str:
    return p.value if p else "unknown"

@dataclass(frozen=True)
class POSAgent:
    cfg: RunConfig
    sponsor_score: float = 0.5  # v1 placeholder (0-1)

    def run_one(self, sp: SciencePacket) -> PoSPacket:
        ta = _map_indication_to_ta(sp.indication)
        base = BASE_RATES.get(_phase_key(sp.phase), BASE_RATES["unknown"]).get(ta, 0.30)

        adjustments: List[PoSAdjustment] = []
        # deterministic adjustment: design quality
        design_delta = (sp.data_quality_score - 0.5) * 0.15
        adjustments.append(PoSAdjustment(name="design_quality", delta=design_delta, rationale="trial design quality vs neutral 0.5"))

        sponsor_delta = (self.sponsor_score - 0.5) * 0.10
        adjustments.append(PoSAdjustment(name="sponsor_track", delta=sponsor_delta, rationale="sponsor score vs neutral 0.5"))

        pos = base + sum(a.delta for a in adjustments)
        pos = max(0.05, min(0.95, pos))

        ci = [max(0.05, pos * 0.8), min(0.95, pos * 1.2)]

        packet_id = f"pos_{deterministic_hash({'ticker': sp.ticker, 'as_of': self.cfg.as_of.isoformat()})}"

        prov = list(sp.provenance) if hasattr(sp, "provenance") else []
        meta = PacketMeta(
            packet_type="pos",
            run_id=self.cfg.to_run_id(),
            as_of=self.cfg.as_of.isoformat(),
            generator="agent2a_pos",
            code_version=self.cfg.code_version,
            provenance=prov,
            suppression=list(sp.suppression) if hasattr(sp, "suppression") else [],
        )

        return PoSPacket(
            meta=meta,
            packet_id=packet_id,
            ticker=sp.ticker,
            base_rate=base,
            final_pos=pos,
            confidence_interval=ci,
            adjustments=adjustments,
            key_drivers=[a.name for a in sorted(adjustments, key=lambda x: abs(x.delta), reverse=True)],
            provenance=prov,
            suppression=list(sp.suppression) if hasattr(sp, "suppression") else [],
        )
