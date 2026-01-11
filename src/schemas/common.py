from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class SuppressionSeverity(str, Enum):
    """Severity levels for data quality suppression flags."""
    info = "info"    # Informational only, no action needed
    warn = "warn"    # Warning, data may be incomplete but usable
    block = "block"  # Critical issue, should halt processing


class ProvenanceRef(BaseModel):
    source: Literal["fixture","manual","api","sec","ctgov","market","other"] = "fixture"
    uri: str = Field(..., description="URL/path/identifier")
    extracted_at: Optional[str] = Field(None, description="ISO8601 extraction timestamp (optional in PIT fixtures)")
    sha256: Optional[str] = None

    model_config = {"frozen": True}

class SuppressionFlag(BaseModel):
    code: str
    severity: Union[SuppressionSeverity, Literal["info", "warn", "block"]] = SuppressionSeverity.warn
    reason: str
    field: Optional[str] = None

    model_config = {"frozen": True}

class PacketMeta(BaseModel):
    schema_version: str = "v1"
    packet_type: str
    run_id: str
    as_of: str
    generator: str
    code_version: str
    provenance: List[ProvenanceRef] = Field(default_factory=list)
    suppression: List[SuppressionFlag] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}
