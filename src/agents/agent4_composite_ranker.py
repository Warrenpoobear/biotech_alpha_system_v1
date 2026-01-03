"""Agent 4: Composite ranker (deterministic v1).

Produces:
  - ScreenResults (JSON) and screen_results.csv (stable order)

Scoring (v1, deterministic heuristics):
  - science_score: based on catalyst horizon + impact tier + design quality
  - pos_score: PoS * 100
  - valuation_score: rNPV / market_cap (if market_cap present) mapped to 0-100
  - setup_score: liquidity proxy from ADV$ mapped to 0-100
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from src.determinism.run_id import RunConfig
from src.determinism.fixtures import FixtureManager
from src.schemas.science_packet import SciencePacket
from src.schemas.pos_packet import PoSPacket
from src.schemas.rnpv_packet import RNPVPacket
from src.schemas.market_packet import MarketPacket
from src.schemas.screen_results import ScreenResult, ScreenResults

def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def _score_science(sp: SciencePacket) -> float:
    # horizon: closer catalysts score higher; unknown horizon is penalized
    if sp.catalyst_horizon_days is None:
        horizon_component = 20.0
    else:
        horizon_component = 100.0 * _clip(1.0 - (sp.catalyst_horizon_days / 365.0), 0.0, 1.0)
    # impact tier: 1 best
    impact_component = 50.0
    if sp.next_catalyst is not None:
        tier = getattr(sp.next_catalyst, "impact_tier", 3) or 3
        impact_component = 100.0 * _clip((6 - float(tier)) / 5.0, 0.0, 1.0)
    # design quality
    dq_component = 100.0 * _clip(sp.data_quality_score, 0.0, 1.0)
    # weighted within science bucket
    return 0.45*horizon_component + 0.30*impact_component + 0.25*dq_component

def _score_pos(pp: PoSPacket) -> float:
    return 100.0 * _clip(pp.final_pos, 0.0, 1.0)

def _score_valuation(rp: RNPVPacket, market_cap: Optional[float]) -> float:
    if not market_cap or market_cap <= 0:
        # can't normalize; return mid with penalty
        return 40.0
    ratio = rp.total_rnpv_usd / market_cap
    # map: 0.25 -> 30, 1.0 -> 70, 2.0 -> 90 (cap at 100)
    if ratio <= 0.25:
        return 30.0 * (ratio / 0.25)
    if ratio <= 1.0:
        return 30.0 + 40.0 * ((ratio - 0.25) / 0.75)
    if ratio <= 2.0:
        return 70.0 + 20.0 * ((ratio - 1.0) / 1.0)
    return 95.0

def _score_setup(mp: MarketPacket) -> float:
    adv = _safe_float(mp.adv_usd, 0.0)
    # map ADV$: <1m -> 10, 5m -> 40, 20m -> 70, 100m -> 95
    if adv <= 1_000_000:
        return 10.0 * (adv / 1_000_000.0)
    if adv <= 5_000_000:
        return 10.0 + 30.0 * ((adv - 1_000_000.0) / 4_000_000.0)
    if adv <= 20_000_000:
        return 40.0 + 30.0 * ((adv - 5_000_000.0) / 15_000_000.0)
    if adv <= 100_000_000:
        return 70.0 + 25.0 * ((adv - 20_000_000.0) / 80_000_000.0)
    return 95.0

@dataclass(frozen=True)
class CompositeRanker:
    cfg: RunConfig
    fixtures_base: Path
    weights_path: Path = Path("config/weights/v1_weights.yaml")

    def _weights(self) -> Dict[str, float]:
        w = yaml.safe_load(self.weights_path.read_text(encoding="utf-8"))
        total = sum(float(v) for v in w.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0; got {total}")
        return {k: float(v) for k, v in w.items()}

    def run(self, packets: Dict[str, Dict[str, Any]]) -> ScreenResults:
        fm = FixtureManager(self.fixtures_base)
        univ = fm.load_df(self.cfg.as_of, "universe")
        # market cap lookup
        mcap = {}
        if "market_cap" in univ.columns:
            for _, r in univ.iterrows():
                mcap[str(r["ticker"]).upper().strip()] = _safe_float(r.get("market_cap"), None)

        weights = self._weights()
        results: List[ScreenResult] = []

        # stable iteration
        for ticker in sorted(packets.keys()):
            sp: SciencePacket = packets[ticker]["science"]
            pp: PoSPacket = packets[ticker]["pos"]
            rp: RNPVPacket = packets[ticker]["rnpv"]
            mp: MarketPacket = packets[ticker]["market"]

            science_score = _score_science(sp)
            pos_score = _score_pos(pp)
            valuation_score = _score_valuation(rp, mcap.get(ticker))
            setup_score = _score_setup(mp)

            composite = (
                science_score * weights["science"] +
                pos_score * weights["pos"] +
                valuation_score * weights["rnpv"] +
                setup_score * weights["setup"]
            )

            # drivers
            comps = {"science": science_score, "pos": pos_score, "valuation": valuation_score, "setup": setup_score}
            drivers = [k for k, _ in sorted(comps.items(), key=lambda kv: kv[1], reverse=True)]

            # binary risk: proximity of next catalyst
            if sp.catalyst_horizon_days is None:
                binary_risk = 0.3
            else:
                binary_risk = _clip(1.0 - (sp.catalyst_horizon_days / 180.0), 0.0, 1.0)

            # dilution risk: simplistic from cash/burn if present
            # if missing => conservative mid
            cash = burn = None
            if "cash" in univ.columns:
                cash = _safe_float(univ[univ["ticker"].astype(str).str.upper().str.strip()==ticker].iloc[0].get("cash"), None) if (univ["ticker"].astype(str).str.upper().str.strip()==ticker).any() else None
            if "burn_rate" in univ.columns:
                burn = _safe_float(univ[univ["ticker"].astype(str).str.upper().str.strip()==ticker].iloc[0].get("burn_rate"), None) if (univ["ticker"].astype(str).str.upper().str.strip()==ticker).any() else None
            if cash and burn and burn > 0:
                runway_months = cash / burn
                dilution_risk = _clip(1.0 - (runway_months / 18.0), 0.0, 1.0)
            else:
                dilution_risk = 0.4

            name = ticker
            if "name" in univ.columns:
                match = univ[univ["ticker"].astype(str).str.upper().str.strip()==ticker]
                if len(match) > 0:
                    name = str(match.iloc[0].get("name") or ticker)

            results.append(ScreenResult(
                ticker=ticker,
                company_name=name,
                as_of=self.cfg.as_of,
                composite_score=_clip(composite, 0.0, 100.0),
                science_score=_clip(science_score, 0.0, 100.0),
                pos_score=_clip(pos_score, 0.0, 100.0),
                valuation_score=_clip(valuation_score, 0.0, 100.0),
                setup_score=_clip(setup_score, 0.0, 100.0),
                primary_driver=drivers[0] if drivers else "insufficient_data",
                secondary_drivers=drivers[1:] if len(drivers)>1 else [],
                suppression_flags=sorted(set(sp.suppression_flags)),
                next_catalyst_days=sp.catalyst_horizon_days,
                next_catalyst_type=(sp.next_catalyst.type.value if sp.next_catalyst else None),
                catalyst_impact_tier=(str(sp.next_catalyst.impact_tier) if sp.next_catalyst else None),
                dilution_risk_90d=_clip(dilution_risk, 0.0, 1.0),
                binary_event_risk_90d=_clip(binary_risk, 0.0, 1.0),
                science_packet_id=sp.packet_id,
                pos_packet_id=pp.packet_id,
                rnpv_packet_id=rp.packet_id,
                market_packet_id=mp.packet_id,
            ))

        # stable sort: composite desc then ticker asc
        results = sorted(results, key=lambda r: (-r.composite_score, r.ticker))
        # Deterministic metadata (no wall-clock time in production outputs)
        generated_at = datetime(self.cfg.as_of.year, self.cfg.as_of.month, self.cfg.as_of.day)
        ms = 0

        return ScreenResults(
            run_id=self.cfg.to_run_id(),
            as_of=self.cfg.as_of,
            universe_version=self.cfg.universe_version,
            ranking_algorithm_version=self.cfg.weights_version,
            results=results,
            ranking_explanation={"weights": weights, "notes": "v1 heuristic scoring"},
            generated_at=generated_at,
            generation_ms=ms,
        )
