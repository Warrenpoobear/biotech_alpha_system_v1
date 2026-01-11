#!/usr/bin/env python3
"""Alpha Engine CLI - Orchestrated pipeline execution.

Usage:
    python -m alpha_engine.run --as-of-date 2024-01-15 --input-dir screener_outputs/

Pipeline stages:
1. Adapt: Convert screener outputs to Alpha Engine contracts
2. Features: Compute features from snapshot bundles
3. Score: Run gates, penalties, and scoring
4. Report: Generate human and machine outputs

Exit codes:
- 0: Success
- 1: Input error (missing files, bad arguments)
- 2: Pipeline error (adapter failure, scoring failure)
- 3: Output error (write failure)
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alpha_engine.contracts import (
    SnapshotBundle,
    FeatureVector,
    ScoreCard,
    RejectionRecord,
    compute_sha256,
    compute_hash_from_dict,
)
from alpha_engine.adapters.biotech_screener import BiotechScreenerAdapter
from alpha_engine.features import FeatureRegistry, create_default_registry
from alpha_engine.scoring import ScoreComposer, ScoringParameters, SCORE_VERSION
from alpha_engine.reporting import ReportConfig, ReportingPipeline


# Exit codes
EXIT_SUCCESS = 0
EXIT_INPUT_ERROR = 1
EXIT_PIPELINE_ERROR = 2
EXIT_OUTPUT_ERROR = 3


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""
    as_of_date: str
    input_dir: Path
    output_dir: Path = field(default_factory=lambda: Path("output"))
    run_id: Optional[str] = None  # Auto-generated if None

    # Input file names (can be customized)
    holdings_file: str = "holdings.json"
    market_data_file: str = "market_data.json"
    financial_data_file: str = "financial_data.json"

    # Checkpointing
    enable_checkpoints: bool = True
    checkpoint_dir: Optional[Path] = None

    # Verbosity
    verbose: bool = False


class PipelineStatus:
    """Tracks pipeline execution status."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.stages_completed: List[str] = []
        self.stage_results: Dict[str, Dict[str, Any]] = {}
        self.errors: List[str] = []

    def start_stage(self, stage: str) -> None:
        """Mark stage as started."""
        if self.verbose:
            print(f"[STAGE] Starting: {stage}")

    def complete_stage(self, stage: str, results: Dict[str, Any]) -> None:
        """Mark stage as completed."""
        self.stages_completed.append(stage)
        self.stage_results[stage] = results
        if self.verbose:
            count = results.get("count", "?")
            print(f"[STAGE] Completed: {stage} ({count} items)")

    def error(self, message: str) -> None:
        """Record an error."""
        self.errors.append(message)
        if self.verbose:
            print(f"[ERROR] {message}", file=sys.stderr)

    def info(self, message: str) -> None:
        """Print info message if verbose."""
        if self.verbose:
            print(f"[INFO] {message}")


def generate_run_id(as_of_date: str, parameters_hash: str) -> str:
    """Generate deterministic run ID from inputs.

    Run ID is based on as_of_date and parameters_hash for reproducibility.
    """
    combined = f"{as_of_date}:{parameters_hash}"
    return compute_sha256(combined)[:16]


def load_json_file(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load JSON file and return (data, error).

    Returns:
        Tuple of (data, None) on success or (None, error_message) on failure.
    """
    if not path.exists():
        return None, f"File not found: {path}"

    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in {path}: {e}"
    except IOError as e:
        return None, f"Error reading {path}: {e}"


def compute_file_hash(path: Path) -> Optional[str]:
    """Compute SHA256 hash of file contents."""
    if not path.exists():
        return None

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class AlphaPipeline:
    """Orchestrates the Alpha Engine pipeline."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.status = PipelineStatus(config.verbose)

        # Initialize components
        self.scoring_params = ScoringParameters()
        self.parameters_hash = self.scoring_params.compute_hash()

        # Generate run_id
        self.run_id = config.run_id or generate_run_id(
            config.as_of_date, self.parameters_hash
        )

        # Track input hashes
        self.input_hashes: Dict[str, str] = {}

    def run(self) -> int:
        """Run the full pipeline.

        Returns exit code.
        """
        self.status.info(f"Alpha Engine Pipeline")
        self.status.info(f"Run ID: {self.run_id}")
        self.status.info(f"As of date: {self.config.as_of_date}")
        self.status.info(f"Input dir: {self.config.input_dir}")

        # Stage 1: Adapt
        bundles = self._stage_adapt()
        if bundles is None:
            return EXIT_INPUT_ERROR

        # Stage 2: Features
        features_by_ticker = self._stage_features(bundles)
        if features_by_ticker is None:
            return EXIT_PIPELINE_ERROR

        # Stage 3: Score
        score_cards, rejections = self._stage_score(bundles, features_by_ticker)
        if score_cards is None:
            return EXIT_PIPELINE_ERROR

        # Stage 4: Report
        success = self._stage_report(score_cards, rejections)
        if not success:
            return EXIT_OUTPUT_ERROR

        self.status.info(f"Pipeline completed successfully")
        return EXIT_SUCCESS

    def _stage_adapt(self) -> Optional[Dict[str, SnapshotBundle]]:
        """Stage 1: Adapt screener outputs to Alpha Engine contracts."""
        self.status.start_stage("Adapt")

        adapter = BiotechScreenerAdapter(as_of_date=self.config.as_of_date)

        # Load holdings data
        holdings_path = self.config.input_dir / self.config.holdings_file
        inst_snaps = {}
        if holdings_path.exists():
            self.input_hashes["holdings"] = compute_file_hash(holdings_path) or ""
            holdings_data, err = load_json_file(holdings_path)
            if err:
                self.status.error(err)
            elif holdings_data:
                inst_snaps, _ = adapter.adapt_holdings(holdings_data)
                self.status.info(f"Loaded {len(inst_snaps)} institutional snapshots")

        # Load market data
        market_path = self.config.input_dir / self.config.market_data_file
        mkt_snaps = {}
        if market_path.exists():
            self.input_hashes["market"] = compute_file_hash(market_path) or ""
            market_data, err = load_json_file(market_path)
            if err:
                self.status.error(err)
            elif market_data:
                mkt_snaps, _ = adapter.adapt_market_data(market_data)
                self.status.info(f"Loaded {len(mkt_snaps)} market snapshots")

        # Load financial data
        financial_path = self.config.input_dir / self.config.financial_data_file
        fin_snaps = {}
        if financial_path.exists():
            self.input_hashes["financial"] = compute_file_hash(financial_path) or ""
            financial_data, err = load_json_file(financial_path)
            if err:
                self.status.error(err)
            elif financial_data:
                fin_snaps, _ = adapter.adapt_financial_data(financial_data)
                self.status.info(f"Loaded {len(fin_snaps)} financial snapshots")

        # Build bundles
        if not mkt_snaps and not inst_snaps and not fin_snaps:
            self.status.error("No input data found")
            return None

        bundles = adapter.build_snapshot_bundles(
            institutional=inst_snaps,
            market=mkt_snaps,
            financial=fin_snaps,
        )

        self.status.complete_stage("Adapt", {"count": len(bundles)})
        return bundles

    def _stage_features(
        self,
        bundles: Dict[str, SnapshotBundle],
    ) -> Optional[Dict[str, FeatureVector]]:
        """Stage 2: Compute features from snapshot bundles."""
        self.status.start_stage("Features")

        registry = create_default_registry()
        features_by_ticker = {}

        for ticker in sorted(bundles.keys()):
            bundle = bundles[ticker]
            features = registry.compute_features(
                bundle,
                score_version=SCORE_VERSION,
                parameters_hash=self.parameters_hash,
                run_id=self.run_id,
            )
            features_by_ticker[ticker] = features

        self.status.complete_stage("Features", {"count": len(features_by_ticker)})
        return features_by_ticker

    def _stage_score(
        self,
        bundles: Dict[str, SnapshotBundle],
        features_by_ticker: Dict[str, FeatureVector],
    ) -> Tuple[Optional[Dict[str, ScoreCard]], Optional[Dict[str, RejectionRecord]]]:
        """Stage 3: Run gates, penalties, and scoring."""
        self.status.start_stage("Score")

        composer = ScoreComposer(
            parameters=self.scoring_params,
            run_id=self.run_id,
        )

        score_cards, rejections = composer.score_bundles(bundles, features_by_ticker)

        scored_count = sum(1 for c in score_cards.values() if c.status.startswith("SCORED"))
        self.status.complete_stage("Score", {
            "count": len(score_cards),
            "scored": scored_count,
            "rejected": len(rejections),
        })

        return score_cards, rejections

    def _stage_report(
        self,
        score_cards: Dict[str, ScoreCard],
        rejections: Dict[str, RejectionRecord],
    ) -> bool:
        """Stage 4: Generate reports."""
        self.status.start_stage("Report")

        try:
            report_config = ReportConfig(output_dir=self.config.output_dir)
            pipeline = ReportingPipeline(report_config)

            output_files = pipeline.generate_all_reports(
                score_cards=score_cards,
                rejections=rejections,
                as_of_date=self.config.as_of_date,
                run_id=self.run_id,
                score_version=SCORE_VERSION,
                parameters_hash=self.parameters_hash,
                input_hashes=self.input_hashes,
                cli_args={
                    "as_of_date": self.config.as_of_date,
                    "input_dir": str(self.config.input_dir),
                    "output_dir": str(self.config.output_dir),
                },
                parameters=self.scoring_params.to_dict(),
            )

            self.status.complete_stage("Report", {
                "count": len(output_files),
                "files": list(output_files.values()),
            })

            if self.config.verbose:
                for name, path in output_files.items():
                    self.status.info(f"  {name}: {path}")

            return True

        except IOError as e:
            self.status.error(f"Failed to write reports: {e}")
            return False


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Alpha Engine Pipeline - Score tickers from screener outputs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--as-of-date",
        required=True,
        help="Point-in-time date for analysis (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        type=Path,
        help="Directory containing screener output files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for output files (default: output/)",
    )
    parser.add_argument(
        "--run-id",
        help="Override auto-generated run ID",
    )
    parser.add_argument(
        "--holdings-file",
        default="holdings.json",
        help="Holdings file name (default: holdings.json)",
    )
    parser.add_argument(
        "--market-data-file",
        default="market_data.json",
        help="Market data file name (default: market_data.json)",
    )
    parser.add_argument(
        "--financial-data-file",
        default="financial_data.json",
        help="Financial data file name (default: financial_data.json)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Alpha Engine {SCORE_VERSION}",
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point.

    Returns exit code.
    """
    parsed = parse_args(args)

    # Validate input directory
    if not parsed.input_dir.exists():
        print(f"Error: Input directory not found: {parsed.input_dir}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    config = PipelineConfig(
        as_of_date=parsed.as_of_date,
        input_dir=parsed.input_dir,
        output_dir=parsed.output_dir,
        run_id=parsed.run_id,
        holdings_file=parsed.holdings_file,
        market_data_file=parsed.market_data_file,
        financial_data_file=parsed.financial_data_file,
        verbose=parsed.verbose,
    )

    pipeline = AlphaPipeline(config)
    return pipeline.run()


if __name__ == "__main__":
    sys.exit(main())
