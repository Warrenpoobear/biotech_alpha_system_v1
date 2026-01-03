from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from .common import PacketMeta, SuppressionFlag, ProvenanceRef

class MarketPacket(BaseModel):
    meta: PacketMeta
    packet_id: str
    ticker: str

    close: Optional[float] = Field(None, ge=0.0)
    volume: Optional[float] = Field(None, ge=0.0)
    adv_usd: Optional[float] = Field(None, ge=0.0)
    short_interest_pct: Optional[float] = Field(None, ge=0.0, le=1.0)

    provenance: List[ProvenanceRef] = Field(default_factory=list)
    suppression: List[SuppressionFlag] = Field(default_factory=list)

    model_config = {"frozen": True}
