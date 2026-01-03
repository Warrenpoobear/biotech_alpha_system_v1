"""Fail-loud validation helpers (quarantine/suppression)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

class QuarantineError(RuntimeError): ...
class ValidationError(RuntimeError): ...

@dataclass(frozen=True)
class SourceCheck:
    source: str
    required_columns: List[str]
    missingness_max: float

@dataclass(frozen=True)
class GateReport:
    run_id: str
    as_of: str
    sources_checked: List[str]
    validation_errors: Dict[str, List[str]]
    quarantine_items: List[str]
    passed_gate: bool

def fail_if_quarantine(report: GateReport) -> None:
    if report.quarantine_items:
        msg = ["ERROR Failed provenance gate (quarantine):"]
        for src in report.quarantine_items:
            errs = report.validation_errors.get(src, [])
            if errs:
                msg.append(f"  - {src}: " + "; ".join(errs))
            else:
                msg.append(f"  - {src}")
        raise QuarantineError("\n".join(msg))
