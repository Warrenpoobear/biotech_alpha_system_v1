"""Canonical output dataclasses for Alpha Engine.

Every output includes:
- score_version: Version of the scoring algorithm
- parameters_hash: SHA256 hash of parameters used
- run_id: Deterministic run identifier
- output_hash: SHA256 hash of this output
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .serialization import canonical_json_dumps, compute_hash_from_dict


class GateStatus(str, Enum):
    """Status of gate checks."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class MissingPolicy(str, Enum):
    """Policy for handling missing data."""
    FAIL_CLOSED = "FAIL_CLOSED"
    UNKNOWN_OK = "UNKNOWN_OK"
    DEFAULT_OK = "DEFAULT_OK"


class RejectionReason(str, Enum):
    """Reasons for rejecting a ticker."""
    LIQUIDITY_GATE = "LIQUIDITY_GATE"
    FINANCIAL_GATE = "FINANCIAL_GATE"
    INTEGRITY_GATE = "INTEGRITY_GATE"
    MISSING_DATA = "MISSING_DATA"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"


@dataclass(frozen=True)
class GateResult:
    """Result of gate checks for a ticker."""
    ticker: str
    gate_name: str
    status: GateStatus
    threshold: Optional[float] = None
    actual_value: Optional[float] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary."""
        return {
            "ticker": self.ticker.upper(),
            "gate_name": self.gate_name,
            "status": self.status.value if isinstance(self.status, GateStatus) else str(self.status),
            "threshold": float(self.threshold) if self.threshold is not None else None,
            "actual_value": float(self.actual_value) if self.actual_value is not None else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RejectionRecord:
    """Record of why a ticker was rejected."""
    ticker: str
    reason: RejectionReason
    gate_results: tuple = field(default_factory=tuple)
    details: Optional[str] = None
    as_of_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary."""
        sorted_gates = sorted(
            [g.to_dict() if hasattr(g, 'to_dict') else g for g in self.gate_results],
            key=lambda x: x.get("gate_name", "")
        )
        return {
            "ticker": self.ticker.upper(),
            "reason": self.reason.value if isinstance(self.reason, RejectionReason) else str(self.reason),
            "gate_results": sorted_gates,
            "details": self.details,
            "as_of_date": self.as_of_date,
        }


@dataclass
class FeatureVector:
    """Computed features for a ticker.

    Contains all features computed for scoring, with provenance tracking.
    """
    ticker: str
    as_of_date: str
    score_version: str
    parameters_hash: str
    run_id: str

    # Feature values (name -> value)
    features: Dict[str, Optional[float]] = field(default_factory=dict)

    # Provenance tracking (feature_name -> list of input hashes used)
    provenance: Dict[str, List[str]] = field(default_factory=dict)

    # Missing features (name -> reason)
    missing_features: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary."""
        return {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "score_version": self.score_version,
            "parameters_hash": self.parameters_hash,
            "run_id": self.run_id,
            "features": {k: float(v) if v is not None else None for k, v in sorted(self.features.items())},
            "provenance": {k: sorted(v) for k, v in sorted(self.provenance.items())},
            "missing_features": dict(sorted(self.missing_features.items())),
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    def compute_output_hash(self) -> str:
        """Compute hash of this feature vector."""
        return compute_hash_from_dict(self.to_dict())


@dataclass
class SignalVector:
    """Signal components for a ticker.

    Intermediate representation between features and final score.
    """
    ticker: str
    as_of_date: str
    score_version: str
    parameters_hash: str
    run_id: str

    # Signal components (name -> value)
    signals: Dict[str, Optional[float]] = field(default_factory=dict)

    # Signal weights used
    weights: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary."""
        return {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "score_version": self.score_version,
            "parameters_hash": self.parameters_hash,
            "run_id": self.run_id,
            "signals": {k: float(v) if v is not None else None for k, v in sorted(self.signals.items())},
            "weights": {k: float(v) for k, v in sorted(self.weights.items())},
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())


@dataclass
class ScoreCard:
    """Final score and components for a ticker.

    Contains the composite alpha score, all components, and status.
    """
    ticker: str
    as_of_date: str
    score_version: str
    parameters_hash: str
    run_id: str

    # Final score
    score_total: float
    status: str  # "SCORED", "REJECTED", "UNKNOWN"

    # Score components
    score_components: Dict[str, float] = field(default_factory=dict)

    # Risk flags
    risk_flags: List[str] = field(default_factory=list)

    # Gate results
    passes_gates: bool = True
    gate_results: List[Dict[str, Any]] = field(default_factory=list)

    # Rejection info (if status == "REJECTED")
    rejection_reasons: List[str] = field(default_factory=list)

    # Provenance
    input_hashes: Dict[str, str] = field(default_factory=dict)
    output_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary."""
        d = {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "score_version": self.score_version,
            "parameters_hash": self.parameters_hash,
            "run_id": self.run_id,
            "score_total": float(self.score_total),
            "status": self.status,
            "score_components": {k: float(v) for k, v in sorted(self.score_components.items())},
            "risk_flags": sorted(self.risk_flags),
            "passes_gates": self.passes_gates,
            "gate_results": sorted(self.gate_results, key=lambda x: x.get("gate_name", "")),
            "rejection_reasons": sorted(self.rejection_reasons),
            "input_hashes": dict(sorted(self.input_hashes.items())),
            "output_hash": self.output_hash,
        }
        return d

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    def compute_output_hash(self) -> str:
        """Compute hash of this score card (excluding output_hash field)."""
        d = self.to_dict()
        d.pop("output_hash", None)
        return compute_hash_from_dict(d)

    def with_output_hash(self) -> "ScoreCard":
        """Return a new ScoreCard with output_hash populated."""
        h = self.compute_output_hash()
        return ScoreCard(
            ticker=self.ticker,
            as_of_date=self.as_of_date,
            score_version=self.score_version,
            parameters_hash=self.parameters_hash,
            run_id=self.run_id,
            score_total=self.score_total,
            status=self.status,
            score_components=self.score_components.copy(),
            risk_flags=self.risk_flags.copy(),
            passes_gates=self.passes_gates,
            gate_results=self.gate_results.copy(),
            rejection_reasons=self.rejection_reasons.copy(),
            input_hashes=self.input_hashes.copy(),
            output_hash=h,
        )


@dataclass
class AuditRecord:
    """Audit record for a pipeline run.

    Contains full provenance for reproducibility.
    """
    run_id: str
    as_of_date: str
    pipeline_version: str
    score_version: str
    parameters_hash: str

    # Input hashes
    input_hashes: Dict[str, str] = field(default_factory=dict)

    # Output hashes
    output_hashes: Dict[str, str] = field(default_factory=dict)

    # CLI args and parameters
    cli_args: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Stage timings (deterministic counters, not wall-clock)
    stage_counts: Dict[str, int] = field(default_factory=dict)

    # Status
    status: str = "COMPLETED"  # COMPLETED, FAILED, PARTIAL
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary."""
        return {
            "run_id": self.run_id,
            "as_of_date": self.as_of_date,
            "pipeline_version": self.pipeline_version,
            "score_version": self.score_version,
            "parameters_hash": self.parameters_hash,
            "input_hashes": dict(sorted(self.input_hashes.items())),
            "output_hashes": dict(sorted(self.output_hashes.items())),
            "cli_args": dict(sorted(self.cli_args.items())),
            "parameters": dict(sorted(self.parameters.items())),
            "stage_counts": dict(sorted(self.stage_counts.items())),
            "status": self.status,
            "error_message": self.error_message,
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    def to_jsonl_line(self) -> str:
        """Serialize to single JSONL line."""
        return canonical_json_dumps(self.to_dict()) + "\n"
