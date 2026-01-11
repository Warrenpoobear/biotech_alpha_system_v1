"""Alpha Engine Contracts - Canonical dataclasses and schemas.

All snapshots include: as_of_date, source_id, input_hash, schema_version
All outputs include: score_version, parameters_hash, run_id (deterministic), output_hash
"""

from .snapshots import (
    MarketSnapshot,
    FinancialSnapshot,
    InstitutionalSnapshot,
    ManagerPosition,
    CatalystSnapshot,
    UniverseSnapshot,
    SnapshotBundle,
)
from .outputs import (
    FeatureVector,
    SignalVector,
    ScoreCard,
    RejectionRecord,
    GateResult,
    AuditRecord,
)
from .serialization import (
    canonical_json_dumps,
    canonical_json_loads,
    compute_sha256,
    compute_hash_from_dict,
    stable_float,
)

__all__ = [
    # Snapshots
    "MarketSnapshot",
    "FinancialSnapshot",
    "InstitutionalSnapshot",
    "ManagerPosition",
    "CatalystSnapshot",
    "UniverseSnapshot",
    "SnapshotBundle",
    # Outputs
    "FeatureVector",
    "SignalVector",
    "ScoreCard",
    "RejectionRecord",
    "GateResult",
    "AuditRecord",
    # Serialization
    "canonical_json_dumps",
    "canonical_json_loads",
    "compute_sha256",
    "compute_hash_from_dict",
    "stable_float",
]
