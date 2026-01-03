from __future__ import annotations

import json
import datetime as dt
from enum import Enum
from pathlib import Path
from typing import Any


def _default_json(x: Any) -> Any:
    """Default encoder for common non-JSON types."""
    if isinstance(x, (dt.date, dt.datetime)):
        # ISO 8601; datetime kept without TZ changes
        return x.isoformat()
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, Enum):
        return x.value
    # Pydantic / dataclass objects that implement `model_dump` / `dict`
    if hasattr(x, "model_dump"):
        try:
            return x.model_dump(mode="json")
        except Exception:
            pass
    if hasattr(x, "dict"):
        try:
            return x.dict()
        except Exception:
            pass
    raise TypeError(f"Object of type {type(x).__name__} is not JSON serializable")


def json_dumps_sorted(obj: Any) -> str:
    """Deterministic JSON serialization.

    - Sorts keys
    - Compact separators
    - Stable handling for date/datetime, Path, Enum

    Prefer passing Pydantic objects as `model_dump(mode=\"json\")` before calling.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default_json,
    )


def write_json(path: Path, obj: Any) -> None:
    """Write deterministic JSON to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps_sorted(obj), encoding="utf-8")
