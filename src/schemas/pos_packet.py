from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .common import PacketMeta, SuppressionFlag, ProvenanceRef

class PoSAdjustment(BaseModel):
    name: str
    delta: float
    rationale: str

    model_config = {"frozen": True}

class PoSPacket(BaseModel):
    meta: PacketMeta
    packet_id: str
    ticker: str
    base_rate: float = Field(..., ge=0.0, le=1.0)
    final_pos: float = Field(..., ge=0.0, le=1.0)
    confidence_interval: List[float] = Field(..., min_length=2, max_length=2)
    adjustments: List[PoSAdjustment] = Field(default_factory=list)
    key_drivers: List[str] = Field(default_factory=list)

    provenance: List[ProvenanceRef] = Field(default_factory=list)
    suppression: List[SuppressionFlag] = Field(default_factory=list)

    model_config = {"frozen": True}
