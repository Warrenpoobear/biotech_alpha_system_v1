"""Deterministic IC dossier generator.

- No timestamps (except as_of / run_id)
- Pure function of packets + screen result
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List

from src.schemas.screen_results import ScreenResult
from src.schemas.science_packet import SciencePacket
from src.schemas.pos_packet import PoSPacket
from src.schemas.rnpv_packet import RNPVPacket
from src.schemas.market_packet import MarketPacket

@dataclass(frozen=True)
class DossierGenerator:
    templates_dir: Path = Path("src/output/templates")

    def generate_one(
        self,
        screen: ScreenResult,
        science: SciencePacket,
        pos: PoSPacket,
        rnpv: RNPVPacket,
        market: MarketPacket,
        run_id: str,
        out_path: Path,
    ) -> str:
        template = (self.templates_dir / "ic_memo_v1.md").read_text(encoding="utf-8")

        next_desc = "None"
        if science.next_catalyst is not None:
            d = science.next_catalyst.date.isoformat() if science.next_catalyst.date else "unknown_date"
            next_desc = f"{science.next_catalyst.type.value} @ {d} (tier={science.next_catalyst.impact_tier})"

        suppressions = sorted(set(science.suppression_flags))
        prov_lines = []
        for p in getattr(science, "provenance", []):
            prov_lines.append(f"- {p.source}: {p.uri}")
        provenance_lines = "\n".join(prov_lines) if prov_lines else "- fixture: (not provided)"

        # deterministic sizing heuristic
        # 0–100 => 0–150 bps (cap), with floor 10 bps if in top list
        position_size_bps = int(max(0, min(150, round(screen.composite_score * 1.5))))
        if position_size_bps > 0 and position_size_bps < 10:
            position_size_bps = 10

        sizing_rationale = f"score-driven heuristic; primary_driver={screen.primary_driver}; run_id={run_id}"

        memo = template.format(
            ticker=screen.ticker,
            as_of=screen.as_of.isoformat(),
            composite_score=screen.composite_score,
            primary_driver=screen.primary_driver,
            next_catalyst_desc=next_desc,
            next_catalyst_days=(screen.next_catalyst_days if screen.next_catalyst_days is not None else "unknown"),
            thesis_bullet_1=f"Upcoming catalyst + {screen.primary_driver} supports near-term asymmetry",
            thesis_bullet_2=f"PoS={pos.final_pos:.2f} with key drivers: {', '.join(pos.key_drivers[:3])}",
            thesis_bullet_3=f"Valuation proxy rNPV=${rnpv.total_rnpv_usd:,.0f} (v1 placeholder model)",
            design_quality=science.data_quality_score,
            pos=pos.final_pos,
            rnpv_usd=rnpv.total_rnpv_usd,
            dilution_risk=screen.dilution_risk_90d,
            binary_risk=screen.binary_event_risk_90d,
            suppressions=(", ".join(suppressions) if suppressions else "none"),
            kill_slip_days=60,
            position_size_bps=position_size_bps,
            sizing_rationale=sizing_rationale,
            provenance_lines=provenance_lines,
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(memo, encoding="utf-8")
        return memo
