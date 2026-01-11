"""Integration tests for the full alpha signal pipeline.

Tests cover:
1. Pipeline execution success
2. Determinism verification (run twice, compare outputs)
3. Fixture builder integration
4. Agent integration chain
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import pytest


# Test date that has universe data
TEST_DATE = date(2024, 1, 1)
TEST_DATE_STR = TEST_DATE.isoformat()


class TestPipelineExecution:
    """Tests for successful pipeline execution."""

    @pytest.fixture
    def work_dir(self, tmp_path):
        """Create a working directory with required files."""
        repo_root = Path(__file__).resolve().parents[1]
        work = tmp_path / "pipeline_test"

        # Copy essential directories
        for subdir in ["src", "config", "data", "fixtures"]:
            src_path = repo_root / subdir
            if src_path.exists():
                shutil.copytree(src_path, work / subdir)

        # Copy pipeline scripts
        for script in [
            "run_pipeline.py",
            "weekly_pipeline_deterministic.py",
            "integrate_agent4.py",
            "define_universe_v2.py",
        ]:
            src_file = repo_root / script
            if src_file.exists():
                shutil.copy(src_file, work / script)

        # Ensure output directories exist
        (work / "output" / "weekly").mkdir(parents=True, exist_ok=True)
        (work / "output" / "agent4").mkdir(parents=True, exist_ok=True)

        yield work

    def test_weekly_pipeline_runs(self, work_dir):
        """Test that weekly_pipeline_deterministic.py runs successfully."""
        result = subprocess.run(
            [sys.executable, "weekly_pipeline_deterministic.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
        assert "WEEKLY PIPELINE COMPLETE" in result.stdout

    def test_weekly_pipeline_creates_outputs(self, work_dir):
        """Test that weekly pipeline creates expected output files."""
        subprocess.run(
            [sys.executable, "weekly_pipeline_deterministic.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
        )

        output_dir = work_dir / "output" / "weekly"
        assert (output_dir / f"detections_{TEST_DATE_STR}.csv").exists()
        assert (output_dir / f"rejections_{TEST_DATE_STR}.csv").exists()
        assert (output_dir / f"summary_{TEST_DATE_STR}.json").exists()
        assert (output_dir / f"audit_{TEST_DATE_STR}.txt").exists()

    def test_agent4_integration_runs(self, work_dir):
        """Test that integrate_agent4.py runs after weekly pipeline."""
        # First run weekly pipeline to create detections
        subprocess.run(
            [sys.executable, "weekly_pipeline_deterministic.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
        )

        # Then run Agent 4 integration
        result = subprocess.run(
            [sys.executable, "integrate_agent4.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Integration failed: {result.stderr}"
        assert "INTEGRATION COMPLETE" in result.stdout

    def test_agent4_creates_outputs(self, work_dir):
        """Test that Agent 4 integration creates expected files."""
        # Run full pipeline
        subprocess.run(
            [sys.executable, "weekly_pipeline_deterministic.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
        )
        subprocess.run(
            [sys.executable, "integrate_agent4.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
        )

        output_dir = work_dir / "output" / "agent4"
        assert (output_dir / f"agent4_signals_{TEST_DATE_STR}.csv").exists()
        assert (output_dir / f"agent4_signals_{TEST_DATE_STR}.json").exists()
        assert (output_dir / f"agent4_hash_{TEST_DATE_STR}.txt").exists()


class TestPipelineDeterminism:
    """Tests for pipeline determinism."""

    @pytest.fixture
    def work_dir(self, tmp_path):
        """Create a working directory with required files."""
        repo_root = Path(__file__).resolve().parents[1]
        work = tmp_path / "determinism_test"

        # Copy essential directories
        for subdir in ["src", "config", "data", "fixtures"]:
            src_path = repo_root / subdir
            if src_path.exists():
                shutil.copytree(src_path, work / subdir)

        # Copy pipeline scripts
        for script in [
            "run_pipeline.py",
            "weekly_pipeline_deterministic.py",
            "integrate_agent4.py",
            "define_universe_v2.py",
        ]:
            src_file = repo_root / script
            if src_file.exists():
                shutil.copy(src_file, work / script)

        yield work

    def _run_pipeline(self, work_dir: Path) -> Dict[str, str]:
        """Run pipeline and return output hashes."""
        # Ensure clean output directories
        output_weekly = work_dir / "output" / "weekly"
        output_agent4 = work_dir / "output" / "agent4"

        shutil.rmtree(output_weekly, ignore_errors=True)
        shutil.rmtree(output_agent4, ignore_errors=True)
        output_weekly.mkdir(parents=True, exist_ok=True)
        output_agent4.mkdir(parents=True, exist_ok=True)

        # Run weekly pipeline
        subprocess.run(
            [sys.executable, "weekly_pipeline_deterministic.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
        )

        # Run Agent 4 integration
        subprocess.run(
            [sys.executable, "integrate_agent4.py", "--date", TEST_DATE_STR],
            cwd=work_dir,
            capture_output=True,
        )

        # Collect hashes of all output files
        hashes = {}

        for output_file in output_weekly.glob("*"):
            if output_file.is_file():
                content = output_file.read_bytes()
                hashes[f"weekly/{output_file.name}"] = hashlib.sha256(content).hexdigest()

        for output_file in output_agent4.glob("*"):
            if output_file.is_file():
                content = output_file.read_bytes()
                hashes[f"agent4/{output_file.name}"] = hashlib.sha256(content).hexdigest()

        return hashes

    def test_pipeline_determinism(self, work_dir):
        """Test that running pipeline twice produces identical outputs."""
        # Run pipeline first time
        hashes_run1 = self._run_pipeline(work_dir)

        # Run pipeline second time
        hashes_run2 = self._run_pipeline(work_dir)

        # Compare hashes
        assert hashes_run1.keys() == hashes_run2.keys(), "Output files differ between runs"

        for key in hashes_run1:
            assert hashes_run1[key] == hashes_run2[key], f"Hash mismatch for {key}"

    def test_detections_content_stable(self, work_dir):
        """Test that detections content is stable between runs."""
        # Run pipeline twice
        self._run_pipeline(work_dir)
        detections1 = pd.read_csv(
            work_dir / "output" / "weekly" / f"detections_{TEST_DATE_STR}.csv"
        )

        self._run_pipeline(work_dir)
        detections2 = pd.read_csv(
            work_dir / "output" / "weekly" / f"detections_{TEST_DATE_STR}.csv"
        )

        # Compare DataFrames
        pd.testing.assert_frame_equal(detections1, detections2)

    def test_agent4_signals_stable(self, work_dir):
        """Test that Agent 4 signals are stable between runs."""
        # Run pipeline twice
        self._run_pipeline(work_dir)
        with open(
            work_dir / "output" / "agent4" / f"agent4_signals_{TEST_DATE_STR}.json"
        ) as f:
            signals1 = json.load(f)

        self._run_pipeline(work_dir)
        with open(
            work_dir / "output" / "agent4" / f"agent4_signals_{TEST_DATE_STR}.json"
        ) as f:
            signals2 = json.load(f)

        assert signals1 == signals2


class TestFixturesBuilder:
    """Tests for fixtures builder integration."""

    def test_demo_fixtures_build(self, tmp_path):
        """Test that demo fixtures can be built."""
        from src.data.fixtures_builder import FixturesBuilder

        universe = pd.DataFrame({
            "ticker": ["MRNA", "GILD", "VRTX"],
            "name": ["Moderna", "Gilead", "Vertex"],
        })

        builder = FixturesBuilder(fixtures_base=tmp_path, use_demo_clients=True)
        refs = builder.build_fixtures_for_date(TEST_DATE, universe)

        # Verify all expected fixture types are created
        assert "clinical_trials" in refs
        assert "regulatory" in refs
        assert "pricing" in refs

        # Verify checksums are valid SHA256 hashes
        for source, sha in refs.items():
            assert len(sha) == 64, f"Invalid hash length for {source}"
            assert all(c in "0123456789abcdef" for c in sha)

    def test_fixtures_determinism(self, tmp_path):
        """Test that fixtures are deterministic."""
        from src.data.fixtures_builder import FixturesBuilder

        universe = pd.DataFrame({
            "ticker": ["MRNA", "GILD"],
            "name": ["Moderna", "Gilead"],
        })

        # Build fixtures twice
        builder1 = FixturesBuilder(fixtures_base=tmp_path / "run1", use_demo_clients=True)
        refs1 = builder1.build_fixtures_for_date(TEST_DATE, universe)

        builder2 = FixturesBuilder(fixtures_base=tmp_path / "run2", use_demo_clients=True)
        refs2 = builder2.build_fixtures_for_date(TEST_DATE, universe)

        # Hashes should match
        assert refs1 == refs2

    def test_fixtures_manifest_created(self, tmp_path):
        """Test that build manifest is created."""
        from src.data.fixtures_builder import FixturesBuilder

        universe = pd.DataFrame({
            "ticker": ["MRNA"],
            "name": ["Moderna"],
        })

        builder = FixturesBuilder(fixtures_base=tmp_path, use_demo_clients=True)
        builder.build_fixtures_for_date(TEST_DATE, universe)

        manifest_path = tmp_path / f"asof={TEST_DATE_STR}" / "fixtures_build_manifest.json"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["as_of"] == TEST_DATE_STR
        assert manifest["fixtures_version"] == "v1"
        assert "outputs" in manifest


class TestAgentChain:
    """Tests for agent integration chain."""

    def test_detection_schema_validation(self):
        """Test that detection records are validated."""
        from integrate_agent4 import validate_detections_df

        # Valid detections
        valid_df = pd.DataFrame({
            "ticker": ["MRNA", "GILD"],
            "score": [0.85, 0.72],
            "signal_id": ["SIG_123", "SIG_456"],
        })

        records = validate_detections_df(valid_df)
        assert len(records) == 2
        assert records[0].ticker == "MRNA"
        assert records[0].score == 0.85

    def test_detection_validation_rejects_invalid(self):
        """Test that invalid detections are rejected."""
        from integrate_agent4 import validate_detections_df

        # Invalid score (> 1.0)
        invalid_df = pd.DataFrame({
            "ticker": ["MRNA"],
            "score": [1.5],  # Invalid: > 1.0
        })

        with pytest.raises(ValueError, match="Validation failed"):
            validate_detections_df(invalid_df)

    def test_agent4_mapping(self):
        """Test Agent 4 signal mapping."""
        from integrate_agent4 import map_to_agent4_format

        detections = pd.DataFrame({
            "ticker": ["MRNA", "GILD"],
            "score": [0.85, 0.72],
        })

        signals = map_to_agent4_format(detections, TEST_DATE_STR)

        assert len(signals) == 2
        assert "security_id" in signals.columns
        assert "alpha_score" in signals.columns
        assert "signal_id" in signals.columns
        assert signals.iloc[0]["security_id"] == "MRNA"
        assert signals.iloc[0]["alpha_score"] == 0.85

    def test_agent4_mapping_deterministic(self):
        """Test that Agent 4 mapping is deterministic."""
        from integrate_agent4 import map_to_agent4_format

        detections = pd.DataFrame({
            "ticker": ["MRNA", "GILD"],
            "score": [0.85, 0.72],
        })

        signals1 = map_to_agent4_format(detections, TEST_DATE_STR)
        signals2 = map_to_agent4_format(detections, TEST_DATE_STR)

        pd.testing.assert_frame_equal(signals1, signals2)

        # Signal IDs should be identical
        assert signals1["signal_id"].tolist() == signals2["signal_id"].tolist()
