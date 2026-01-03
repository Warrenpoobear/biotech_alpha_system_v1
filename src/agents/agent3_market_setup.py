"""Agent 3: Market setup (fixture-driven, minimal)."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.determinism.run_id import RunConfig
from src.determinism.fixtures import FixtureManager
from src.determinism.hashing import deterministic_hash
from src.schemas.common import PacketMeta, ProvenanceRef
from src.schemas.market_packet import MarketPacket

def _f(x) -> Optional[float]:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return float(x)
    except Exception:
        return None

@dataclass(frozen=True)
class MarketSetupAgent:
    cfg: RunConfig
    fixtures_base: Path

    def run(self, tickers: List[str]) -> Dict[str, MarketPacket]:
        fm = FixtureManager(self.fixtures_base)
        px = fm.load_df(self.cfg.as_of, "pricing")
        out: Dict[str, MarketPacket] = {}
        for t in sorted(tickers):
            out[t] = self._one(t, px)
        return out

    def _one(self, ticker: str, px: pd.DataFrame) -> MarketPacket:
        tt = px[px["ticker"].astype(str).str.upper().str.strip() == ticker].copy()
        if len(tt) > 0:
            tt = tt.sort_values(by=["ticker"], kind="mergesort")
            row = tt.iloc[0]
            close = _f(row.get("close"))
            vol = _f(row.get("volume"))
            shares = _f(row.get("shares_outstanding"))
            adv_usd = (close * vol) if (close is not None and vol is not None) else None
        else:
            close = vol = shares = adv_usd = None

        prov = [ProvenanceRef(source="fixture", uri=f"fixtures/asof={self.cfg.as_of.isoformat()}/pricing")]
        meta = PacketMeta(
            packet_type="market",
            run_id=self.cfg.to_run_id(),
            as_of=self.cfg.as_of.isoformat(),
            generator="agent3_market_setup",
            code_version=self.cfg.code_version,
            provenance=prov,
        )
        packet_id = f"market_{deterministic_hash({'ticker': ticker, 'as_of': self.cfg.as_of.isoformat()})}"
        return MarketPacket(
            meta=meta,
            packet_id=packet_id,
            ticker=ticker,
            close=close,
            volume=vol,
            adv_usd=adv_usd,
            short_interest_pct=None,
            provenance=prov,
            suppression=[],
        )
