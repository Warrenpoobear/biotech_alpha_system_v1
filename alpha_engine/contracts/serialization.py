"""Canonical serialization and hashing utilities.

Guarantees:
- Sorted keys in all JSON output
- Stable float formatting (8 decimal places)
- No NaN/Infinity (converted to null)
- Deterministic sha256 hashing
"""

from __future__ import annotations
import hashlib
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union


# Float precision for canonical representation
FLOAT_PRECISION = 8


def stable_float(value: Optional[float], precision: int = FLOAT_PRECISION) -> Optional[str]:
    """Convert float to stable string representation.

    Returns None for None/NaN/Infinity, otherwise formats to fixed precision.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:  # NaN check
            return None
        if value == float('inf') or value == float('-inf'):
            return None
    return f"{float(value):.{precision}f}"


def _normalize_value(value: Any) -> Any:
    """Normalize a value for canonical JSON serialization."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        if value == float('inf') or value == float('-inf'):
            return None
        # Format to stable precision
        return round(value, FLOAT_PRECISION)
    if isinstance(value, Decimal):
        return round(float(value), FLOAT_PRECISION)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize_value(v) for k, v in sorted(value.items())}
    if hasattr(value, '__dict__'):
        return _normalize_value(vars(value))
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


class CanonicalEncoder(json.JSONEncoder):
    """JSON encoder that produces deterministic output."""

    def default(self, obj: Any) -> Any:
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        if hasattr(obj, '__dict__'):
            return _normalize_value(vars(obj))
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

    def encode(self, obj: Any) -> str:
        normalized = _normalize_value(obj)
        return super().encode(normalized)


def canonical_json_dumps(obj: Any, indent: Optional[int] = None) -> str:
    """Serialize object to canonical JSON string.

    Guarantees:
    - Sorted keys
    - Stable float formatting
    - No NaN/Infinity (converted to null)
    - Deterministic output for same input
    """
    normalized = _normalize_value(obj)
    return json.dumps(
        normalized,
        cls=CanonicalEncoder,
        sort_keys=True,
        indent=indent,
        ensure_ascii=False,
        separators=(',', ':') if indent is None else (',', ': ')
    )


def canonical_json_loads(s: str) -> Any:
    """Deserialize canonical JSON string."""
    return json.loads(s)


def compute_sha256(data: Union[str, bytes]) -> str:
    """Compute SHA256 hash of string or bytes."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def compute_hash_from_dict(d: Dict[str, Any]) -> str:
    """Compute deterministic SHA256 hash of a dictionary.

    Uses canonical JSON serialization to ensure stability.
    """
    canonical = canonical_json_dumps(d)
    return compute_sha256(canonical)


def compute_hash_from_dataclass(obj: Any) -> str:
    """Compute deterministic SHA256 hash of a dataclass instance."""
    if hasattr(obj, 'to_dict'):
        return compute_hash_from_dict(obj.to_dict())
    if hasattr(obj, '__dict__'):
        return compute_hash_from_dict(vars(obj))
    raise TypeError(f"Cannot compute hash for type: {type(obj)}")
