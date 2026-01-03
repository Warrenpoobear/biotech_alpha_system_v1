from __future__ import annotations
import datetime as dt
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from .common import PacketMeta, ProvenanceRef, SuppressionFlag

class TrialPhase(str, Enum):
    phase1 = "phase1"
    phase2 = "phase2"
    phase3 = "phase3"
    phase4 = "phase4"
    pivotal = "pivotal"
    unknown = "unknown"

class CatalystType(str, Enum):
    topline_results = "topline_results"
    regulatory_submission = "regulatory_submission"
    adcomm_meeting = "adcomm_meeting"
    pdufa_date = "pdufa_date"
    ema_chmp = "ema_chmp"
    conference_presentation = "conference_presentation"
    data_update = "data_update"
    other = "other"

class Catalyst(BaseModel):
    type: CatalystType
    date: Optional[dt.date] = None
    description: str
    impact_tier: int = Field(3, ge=1, le=5)
    source: str
    source_uri: Optional[str] = None

    model_config = {"frozen": True}

class SciencePacket(BaseModel):
    meta: PacketMeta
    packet_id: str
    as_of: dt.date
    extraction_timestamp: str

    ticker: str = Field(..., min_length=1, max_length=10)
    drug_name: str = Field(..., min_length=1)
    indication: str = Field(..., min_length=1)
    mechanism_of_action: Optional[str] = None

    trial_id: str = Field(..., pattern=r"^NCT\d{8}$")
    phase: TrialPhase

    enrollment_target: Optional[int] = Field(None, ge=1)
    enrollment_actual: Optional[int] = Field(None, ge=0)

    is_randomized: bool = False
    is_controlled: bool = False
    is_blinded: bool = False
    is_powered: bool = False
    primary_endpoint: str = Field(..., min_length=1)
    statistical_plan: Optional[str] = None

    catalysts: List[Catalyst] = Field(default_factory=list)
    next_catalyst: Optional[Catalyst] = None
    catalyst_horizon_days: Optional[int] = Field(None, ge=0)

    source_urls: List[str] = Field(default_factory=list)
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)

    suppression_flags: List[str] = Field(default_factory=list)
    data_quality_score: float = Field(..., ge=0.0, le=1.0)

    provenance: List[ProvenanceRef] = Field(default_factory=list)
    suppression: List[SuppressionFlag] = Field(default_factory=list)

    model_config = {"frozen": True}

    @field_validator("catalysts")
    @classmethod
    def validate_catalysts(cls, v: List[Catalyst]):
        # structure enforced by Catalyst model
        return v

    @field_validator("extraction_confidence")
    @classmethod
    def confidence_requires_sources(cls, v: float, info):
        data = info.data
        if v > 0.8 and len(data.get("source_urls", [])) < 2:
            raise ValueError("High confidence requires ≥2 source_urls")
        return v
