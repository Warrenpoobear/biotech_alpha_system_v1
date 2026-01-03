"""Deterministic run ID generation and verification."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict
from .hashing import deterministic_hash

@dataclass(frozen=True)
class RunConfig:
    """Immutable run configuration."""
    as_of: date
    universe_version: str
    code_version: str
    weights_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "universe_version": self.universe_version,
            "code_version": self.code_version,
            "weights_version": self.weights_version,
        }

    def to_run_id(self) -> str:
        return deterministic_hash(self.to_dict())
