"""Agent 0: Data Quality & Provenance Gate (fail-loud).

v1 focuses on:
- fixture presence
- required columns
- basic missingness threshold per required columns
- emits a GateReport (used to hard-stop on quarantine)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yaml

from src.determinism.run_id import RunConfig
from src.determinism.fixtures import FixtureManager, FixtureMissingError, FixtureValidationError
from src.determinism.validation import GateReport

@dataclass(frozen=True)
class ProvenanceGateConfig:
    required_sources: Dict[str, List[str]]
    max_required_missing_pct: float = 0.30

    @staticmethod
    def load(path: Path) -> "ProvenanceGateConfig":
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
        req = obj.get("required_sources", [])
        # Allow either list or dict
        if isinstance(req, list):
            # default columns minimal; user can expand later
            required_sources = {k: ["ticker"] for k in req}
        else:
            required_sources = {str(k): list(v) for k, v in req.items()}
        qt = obj.get("quarantine_thresholds", {}) or {}
        return ProvenanceGateConfig(
            required_sources=required_sources,
            max_required_missing_pct=float(qt.get("max_required_missing_pct", 0.30)),
        )

class ProvenanceGate:
    def __init__(self, config: RunConfig, fixtures_base: Path, artifacts_dir: Path, rules_path: Path = Path("config/suppression_rules.yaml")):
        self.config = config
        self.fixtures = FixtureManager(fixtures_base)
        self.artifacts_dir = artifacts_dir
        self.rules = ProvenanceGateConfig.load(rules_path)

    def run(self) -> GateReport:
        errors: Dict[str, List[str]] = {}
        quarantine: List[str] = []
        checked: List[str] = []

        for source, required_cols in self.rules.required_sources.items():
            checked.append(source)
            try:
                df = self.fixtures.load_df(self.config.as_of, source, required_columns=required_cols)
                # Missingness check on required columns
                miss = df[required_cols].isna().mean().max() if len(df) else 1.0
                if miss > self.rules.max_required_missing_pct:
                    quarantine.append(source)
                    errors.setdefault(source, []).append(f"High missingness in required cols: {miss:.1%} > {self.rules.max_required_missing_pct:.0%}")
            except FixtureMissingError as e:
                quarantine.append(source)
                errors.setdefault(source, []).append(str(e))
            except FixtureValidationError as e:
                quarantine.append(source)
                errors.setdefault(source, []).append(str(e))

        report = GateReport(
            run_id=self.config.to_run_id(),
            as_of=self.config.as_of.isoformat(),
            sources_checked=checked,
            validation_errors=errors,
            quarantine_items=quarantine,
            passed_gate=(len(quarantine) == 0),
        )

        # Persist report deterministically
        out = {
            "run_id": report.run_id,
            "as_of": report.as_of,
            "sources_checked": report.sources_checked,
            "validation_errors": report.validation_errors,
            "quarantine_items": report.quarantine_items,
            "passed_gate": report.passed_gate,
        }
        (self.artifacts_dir / "provenance_report.json").write_text(
            json_dumps_sorted(out),
            encoding="utf-8",
        )
        return report

def json_dumps_sorted(obj) -> str:
    import json
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
