"""Reporting Module - Human and machine-readable outputs.

Outputs:
- alpha_scores.json: Canonical JSON array of ScoreCard
- ALPHA_ENGINE_REPORT.txt: Human-readable summary
- audit_log.jsonl: Append-only JSONL of AuditRecord

All outputs are deterministic given the same inputs.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alpha_engine.contracts import (
    ScoreCard,
    RejectionRecord,
    AuditRecord,
    canonical_json_dumps,
    compute_hash_from_dict,
)


# Pipeline version for audit tracking
PIPELINE_VERSION = "1.0.0"


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    output_dir: Path = field(default_factory=lambda: Path("output"))
    scores_filename: str = "alpha_scores.json"
    report_filename: str = "ALPHA_ENGINE_REPORT.txt"
    audit_filename: str = "audit_log.jsonl"

    # Report settings
    top_n_scores: int = 20
    show_risk_flags: bool = True
    show_unknown_flags: bool = True


class ScoreReporter:
    """Generates human and machine-readable reports from scored data."""

    def __init__(self, config: Optional[ReportConfig] = None):
        self.config = config or ReportConfig()

    def write_scores_json(
        self,
        score_cards: Dict[str, ScoreCard],
        output_path: Optional[Path] = None,
    ) -> str:
        """Write canonical JSON array of score cards.

        Returns the file path written.
        """
        output_path = output_path or (self.config.output_dir / self.config.scores_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Sort by ticker for determinism
        sorted_cards = [
            score_cards[ticker].to_dict()
            for ticker in sorted(score_cards.keys())
        ]

        json_content = canonical_json_dumps(sorted_cards)

        with open(output_path, "w") as f:
            f.write(json_content)

        return str(output_path)

    def generate_human_report(
        self,
        score_cards: Dict[str, ScoreCard],
        rejections: Dict[str, RejectionRecord],
        as_of_date: str,
        run_id: str,
    ) -> str:
        """Generate human-readable report text.

        Returns the report content as a string.
        """
        lines = []

        # Header
        lines.append("=" * 70)
        lines.append("ALPHA ENGINE REPORT")
        lines.append("=" * 70)
        lines.append(f"As of Date: {as_of_date}")
        lines.append(f"Run ID: {run_id}")
        lines.append(f"Generated: [deterministic - see audit log]")
        lines.append("")

        # Summary statistics
        total_tickers = len(score_cards) + len(rejections)
        scored_count = sum(1 for c in score_cards.values() if c.status.startswith("SCORED"))
        rejected_count = len(rejections)
        low_confidence_count = sum(
            1 for c in score_cards.values() if c.status == "SCORED_LOW_CONFIDENCE"
        )

        lines.append("-" * 70)
        lines.append("SUMMARY")
        lines.append("-" * 70)
        lines.append(f"Total Tickers:     {total_tickers}")
        lines.append(f"Scored:            {scored_count}")
        lines.append(f"Rejected:          {rejected_count}")
        lines.append(f"Low Confidence:    {low_confidence_count}")
        lines.append("")

        # Top scores
        lines.append("-" * 70)
        lines.append(f"TOP {self.config.top_n_scores} ALPHA SIGNALS")
        lines.append("-" * 70)

        scored_list = [
            c for c in score_cards.values()
            if c.status.startswith("SCORED")
        ]
        top_scored = sorted(
            scored_list,
            key=lambda x: x.score_total,
            reverse=True
        )[:self.config.top_n_scores]

        if top_scored:
            lines.append(f"{'Rank':<5} {'Ticker':<10} {'Score':<8} {'Status':<20} {'Risk Flags':<30}")
            lines.append("-" * 70)

            for i, card in enumerate(top_scored, 1):
                flags = ", ".join(card.risk_flags) if card.risk_flags else "-"
                lines.append(
                    f"{i:<5} {card.ticker:<10} {card.score_total:>6.2%} {card.status:<20} {flags:<30}"
                )
        else:
            lines.append("No scored tickers.")
        lines.append("")

        # Risk flags summary
        if self.config.show_risk_flags:
            lines.append("-" * 70)
            lines.append("RISK FLAGS SUMMARY")
            lines.append("-" * 70)

            flag_counts: Dict[str, int] = {}
            for card in score_cards.values():
                for flag in card.risk_flags:
                    flag_counts[flag] = flag_counts.get(flag, 0) + 1

            if flag_counts:
                for flag, count in sorted(flag_counts.items()):
                    lines.append(f"  {flag}: {count} ticker(s)")
            else:
                lines.append("  No risk flags triggered.")
            lines.append("")

        # Rejections
        lines.append("-" * 70)
        lines.append("REJECTIONS (Gate Failures)")
        lines.append("-" * 70)

        if rejections:
            lines.append(f"{'Ticker':<10} {'Reason':<25} {'Details':<35}")
            lines.append("-" * 70)

            for ticker in sorted(rejections.keys()):
                rej = rejections[ticker]
                reason_str = str(rej.reason.value) if hasattr(rej.reason, 'value') else str(rej.reason)
                details = rej.details[:35] if rej.details else "-"
                lines.append(f"{ticker:<10} {reason_str:<25} {details:<35}")
        else:
            lines.append("No tickers rejected.")
        lines.append("")

        # Unknown/Partial data summary
        if self.config.show_unknown_flags:
            lines.append("-" * 70)
            lines.append("UNKNOWN DATA FLAGS")
            lines.append("-" * 70)

            partial_tickers = [
                c.ticker for c in score_cards.values()
                if c.status in ("SCORED_PARTIAL", "SCORED_LOW_CONFIDENCE")
            ]

            if partial_tickers:
                lines.append("Tickers with missing data components:")
                for ticker in sorted(partial_tickers)[:20]:
                    card = score_cards[ticker]
                    lines.append(f"  {ticker}: {card.status}")
                if len(partial_tickers) > 20:
                    lines.append(f"  ... and {len(partial_tickers) - 20} more")
            else:
                lines.append("All scored tickers have complete data.")
            lines.append("")

        # Score component breakdown for top 5
        lines.append("-" * 70)
        lines.append("SCORE BREAKDOWN (Top 5)")
        lines.append("-" * 70)

        for card in top_scored[:5]:
            lines.append(f"\n{card.ticker}:")
            lines.append(f"  Total Score: {card.score_total:.2%}")
            for comp_name, comp_value in sorted(card.score_components.items()):
                lines.append(f"  - {comp_name}: {comp_value:.4f}")

        # Footer
        lines.append("")
        lines.append("=" * 70)
        lines.append("END OF REPORT")
        lines.append("=" * 70)

        return "\n".join(lines)

    def write_human_report(
        self,
        score_cards: Dict[str, ScoreCard],
        rejections: Dict[str, RejectionRecord],
        as_of_date: str,
        run_id: str,
        output_path: Optional[Path] = None,
    ) -> str:
        """Write human-readable report to file.

        Returns the file path written.
        """
        output_path = output_path or (self.config.output_dir / self.config.report_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        content = self.generate_human_report(score_cards, rejections, as_of_date, run_id)

        with open(output_path, "w") as f:
            f.write(content)

        return str(output_path)


class AuditLogger:
    """Append-only audit logger for pipeline runs."""

    def __init__(self, config: Optional[ReportConfig] = None):
        self.config = config or ReportConfig()

    def create_audit_record(
        self,
        run_id: str,
        as_of_date: str,
        score_version: str,
        parameters_hash: str,
        input_hashes: Dict[str, str],
        output_hashes: Dict[str, str],
        cli_args: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        stage_counts: Optional[Dict[str, int]] = None,
        status: str = "COMPLETED",
        error_message: Optional[str] = None,
    ) -> AuditRecord:
        """Create an audit record for a pipeline run."""
        return AuditRecord(
            run_id=run_id,
            as_of_date=as_of_date,
            pipeline_version=PIPELINE_VERSION,
            score_version=score_version,
            parameters_hash=parameters_hash,
            input_hashes=input_hashes,
            output_hashes=output_hashes,
            cli_args=cli_args or {},
            parameters=parameters or {},
            stage_counts=stage_counts or {},
            status=status,
            error_message=error_message,
        )

    def append_audit_record(
        self,
        record: AuditRecord,
        output_path: Optional[Path] = None,
    ) -> str:
        """Append an audit record to the JSONL log.

        Returns the file path written.
        """
        output_path = output_path or (self.config.output_dir / self.config.audit_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        line = record.to_jsonl_line()

        with open(output_path, "a") as f:
            f.write(line)

        return str(output_path)

    def read_audit_log(
        self,
        input_path: Optional[Path] = None,
    ) -> List[AuditRecord]:
        """Read all audit records from the log file."""
        input_path = input_path or (self.config.output_dir / self.config.audit_filename)

        if not input_path.exists():
            return []

        records = []
        with open(input_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    import json
                    d = json.loads(line)
                    record = AuditRecord(
                        run_id=d["run_id"],
                        as_of_date=d["as_of_date"],
                        pipeline_version=d["pipeline_version"],
                        score_version=d["score_version"],
                        parameters_hash=d["parameters_hash"],
                        input_hashes=d.get("input_hashes", {}),
                        output_hashes=d.get("output_hashes", {}),
                        cli_args=d.get("cli_args", {}),
                        parameters=d.get("parameters", {}),
                        stage_counts=d.get("stage_counts", {}),
                        status=d.get("status", "UNKNOWN"),
                        error_message=d.get("error_message"),
                    )
                    records.append(record)

        return records


def compute_output_hashes(
    score_cards: Dict[str, ScoreCard],
    rejections: Dict[str, RejectionRecord],
) -> Dict[str, str]:
    """Compute hashes for all output artifacts.

    Returns dict with:
    - scores_hash: Hash of all score cards
    - rejections_hash: Hash of all rejections
    """
    # Hash score cards (sorted by ticker)
    scores_data = [
        score_cards[ticker].to_dict()
        for ticker in sorted(score_cards.keys())
    ]
    scores_hash = compute_hash_from_dict({"scores": scores_data})

    # Hash rejections (sorted by ticker)
    rejections_data = [
        rejections[ticker].to_dict()
        for ticker in sorted(rejections.keys())
    ]
    rejections_hash = compute_hash_from_dict({"rejections": rejections_data})

    return {
        "scores_hash": scores_hash,
        "rejections_hash": rejections_hash,
    }


class ReportingPipeline:
    """Combined reporting pipeline for generating all outputs."""

    def __init__(self, config: Optional[ReportConfig] = None):
        self.config = config or ReportConfig()
        self.score_reporter = ScoreReporter(self.config)
        self.audit_logger = AuditLogger(self.config)

    def generate_all_reports(
        self,
        score_cards: Dict[str, ScoreCard],
        rejections: Dict[str, RejectionRecord],
        as_of_date: str,
        run_id: str,
        score_version: str,
        parameters_hash: str,
        input_hashes: Dict[str, str],
        cli_args: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Generate all report outputs.

        Returns dict of output file paths.
        """
        output_files = {}

        # Write scores JSON
        output_files["scores_json"] = self.score_reporter.write_scores_json(score_cards)

        # Write human report
        output_files["human_report"] = self.score_reporter.write_human_report(
            score_cards, rejections, as_of_date, run_id
        )

        # Compute output hashes
        output_hashes = compute_output_hashes(score_cards, rejections)

        # Create and append audit record
        audit_record = self.audit_logger.create_audit_record(
            run_id=run_id,
            as_of_date=as_of_date,
            score_version=score_version,
            parameters_hash=parameters_hash,
            input_hashes=input_hashes,
            output_hashes=output_hashes,
            cli_args=cli_args,
            parameters=parameters,
            stage_counts={
                "scored": len([c for c in score_cards.values() if c.status.startswith("SCORED")]),
                "rejected": len(rejections),
            },
        )
        output_files["audit_log"] = self.audit_logger.append_audit_record(audit_record)

        return output_files
