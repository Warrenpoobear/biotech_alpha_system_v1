"""Deterministic hashing + canonical JSON (contract v1)."""

from __future__ import annotations
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict

_Q = Decimal("0.00000001")  # 8dp per v1 spec

def _round_float(x: float) -> str:
    d = Decimal(repr(x)).quantize(_Q, rounding=ROUND_HALF_UP)
    # Avoid scientific notation; trim trailing zeros
    s = format(d, "f").rstrip("0").rstrip(".")
    return s if s else "0"

def canonicalize(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        # Represent as deterministic string to avoid float JSON variation
        return _round_float(obj)
    if isinstance(obj, dict):
        return {k: canonicalize(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, (list, tuple)):
        return [canonicalize(x) for x in obj]
    # Fallback
    return str(obj)

def canonical_json(data: Dict[str, Any]) -> str:
    can = canonicalize(data)
    return json.dumps(can, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def deterministic_hash(data: Dict[str, Any], n: int = 16) -> str:
    """Stable SHA256 hash truncated to n chars (default 16)."""
    s = canonical_json(data)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]
