"""Agent 2B: rNPV (simplified v1).

Goal: provide deterministic valuation scaffolding without external dependencies.
- Uses 3 scenarios (bear/base/bull) with fixed discounting.
- In v1, peak revenue is a placeholder; wire to TAM/pricing model later.

Output: RNPVPacket
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List

from src.determinism.run_id import RunConfig
from src.determinism.hashing import deterministic_hash
from src.schemas.common import PacketMeta
from src.schemas.science_packet import SciencePacket
from src.schemas.pos_packet import PoSPacket
from src.schemas.rnpv_packet import RNPVPacket, Scenario, ScenarioName

def _pv_factor(discount_rate: float, years: int) -> float:
    # deterministic: (1+r)^-years
    return (1.0 / ((1.0 + discount_rate) ** years)) if years >= 0 else 1.0

@dataclass(frozen=True)
class RNPVAgent:
    cfg: RunConfig

    def run_one(self, sp: SciencePacket, pp: PoSPacket) -> RNPVPacket:
        # Placeholder peak revenue: $500m base, scaled by phase
        phase_mult = {
            "phase1": 0.4, "phase2": 0.7, "phase3": 1.0, "pivotal": 1.1, "phase4": 1.2, "unknown": 0.6
        }.get(sp.phase.value, 0.6)

        base_peak = 500_000_000.0 * phase_mult
        scenarios: List[Scenario] = [
            Scenario(name=ScenarioName.bear, probability=0.25, revenue_peak_usd=base_peak*0.6, margin=0.55, discount_rate=0.12, years_to_peak=5, notes="v1 placeholder"),
            Scenario(name=ScenarioName.base, probability=0.50, revenue_peak_usd=base_peak*1.0, margin=0.65, discount_rate=0.12, years_to_peak=4, notes="v1 placeholder"),
            Scenario(name=ScenarioName.bull, probability=0.25, revenue_peak_usd=base_peak*1.6, margin=0.70, discount_rate=0.12, years_to_peak=3, notes="v1 placeholder"),
        ]

        # Very rough PV: peak*margin*PV * PoS
        # Use expected PV across scenarios weighted by scenario probabilities (independent of PoS).
        ev = 0.0
        for sc in scenarios:
            ev += sc.probability * (sc.revenue_peak_usd * sc.margin * _pv_factor(sc.discount_rate, sc.years_to_peak))

        total = max(0.0, pp.final_pos * ev)

        packet_id = f"rnpv_{deterministic_hash({'ticker': sp.ticker, 'as_of': self.cfg.as_of.isoformat()})}"

        meta = PacketMeta(
            packet_type="rnpv",
            run_id=self.cfg.to_run_id(),
            as_of=self.cfg.as_of.isoformat(),
            generator="agent2b_rnpv",
            code_version=self.cfg.code_version,
            provenance=list(sp.provenance),
            suppression=list(sp.suppression),
        )

        return RNPVPacket(
            meta=meta,
            packet_id=packet_id,
            ticker=sp.ticker,
            total_rnpv_usd=total,
            scenarios=scenarios,
            provenance=list(sp.provenance),
            suppression=list(sp.suppression),
        )
