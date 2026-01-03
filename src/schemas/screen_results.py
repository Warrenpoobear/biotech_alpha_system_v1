from __future__ import annotations
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ScreenResult(BaseModel):
    ticker: str
    company_name: str
    as_of: date

    composite_score: float = Field(..., ge=0.0, le=100.0)
    science_score: float = Field(..., ge=0.0, le=100.0)
    pos_score: float = Field(..., ge=0.0, le=100.0)
    valuation_score: float = Field(..., ge=0.0, le=100.0)
    setup_score: float = Field(..., ge=0.0, le=100.0)

    primary_driver: str
    secondary_drivers: List[str] = Field(default_factory=list)
    suppression_flags: List[str] = Field(default_factory=list)

    next_catalyst_days: Optional[int] = Field(None, ge=0)
    next_catalyst_type: Optional[str] = None
    catalyst_impact_tier: Optional[str] = None

    dilution_risk_90d: float = Field(..., ge=0.0, le=1.0)
    binary_event_risk_90d: float = Field(..., ge=0.0, le=1.0)

    science_packet_id: Optional[str] = None
    pos_packet_id: Optional[str] = None
    rnpv_packet_id: Optional[str] = None
    market_packet_id: Optional[str] = None

    model_config = {"frozen": True}

class ScreenResults(BaseModel):
    run_id: str
    as_of: date
    universe_version: str
    ranking_algorithm_version: str

    results: List[ScreenResult]
    ranking_explanation: Dict[str, Any] = Field(default_factory=dict)

    generated_at: datetime
    generation_ms: int = Field(..., ge=0)

    model_config = {"frozen": True}
