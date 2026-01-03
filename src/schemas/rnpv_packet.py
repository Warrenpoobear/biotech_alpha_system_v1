from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from .common import PacketMeta, SuppressionFlag, ProvenanceRef

class ScenarioName(str, Enum):
    bear = "bear"
    base = "base"
    bull = "bull"

class Scenario(BaseModel):
    name: ScenarioName
    probability: float = Field(..., ge=0.0, le=1.0)
    revenue_peak_usd: float = Field(..., ge=0.0)
    margin: float = Field(..., ge=0.0, le=1.0)
    discount_rate: float = Field(..., ge=0.0, le=1.0)
    years_to_peak: int = Field(..., ge=0)
    notes: Optional[str] = None

    model_config = {"frozen": True}

class RNPVPacket(BaseModel):
    meta: PacketMeta
    packet_id: str
    ticker: str
    total_rnpv_usd: float = Field(..., ge=0.0)
    scenarios: List[Scenario] = Field(default_factory=list)

    provenance: List[ProvenanceRef] = Field(default_factory=list)
    suppression: List[SuppressionFlag] = Field(default_factory=list)

    model_config = {"frozen": True}
