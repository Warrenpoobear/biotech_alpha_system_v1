"""Tests for Reporting Module."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from alpha_engine.contracts import ScoreCard, RejectionRecord, AuditRecord
from alpha_engine.contracts.outputs import RejectionReason
from alpha_engine.reporting import (
    ReportConfig,
    ScoreReporter,
    AuditLogger,
    ReportingPipeline,
    compute_output_hashes,
    PIPELINE_VERSION,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_score_cards():
    """Create sample score cards for testing."""
    return {
        "MRNA": ScoreCard(
            ticker="MRNA",
            as_of_date="2024-01-15",
            score_version="1.0.0",
            parameters_hash="a" * 64,
            run_id="test_run",
            score_total=0.75,
            status="SCORED",
            score_components={
                "institutional_score": 0.80,
                "liquidity_score": 0.70,
                "catalyst_score": 0.65,
                "momentum_score": 0.50,
            },
            risk_flags=["RISK_CONCENTRATION"],
        ),
        "GILD": ScoreCard(
            ticker="GILD",
            as_of_date="2024-01-15",
            score_version="1.0.0",
            parameters_hash="a" * 64,
            run_id="test_run",
            score_total=0.65,
            status="SCORED_PARTIAL",
            score_components={
                "institutional_score": 0.70,
                "liquidity_score": 0.60,
                "catalyst_score": 0.50,
                "momentum_score": 0.50,
            },
        ),
        "VRTX": ScoreCard(
            ticker="VRTX",
            as_of_date="2024-01-15",
            score_version="1.0.0",
            parameters_hash="a" * 64,
            run_id="test_run",
            score_total=0.55,
            status="SCORED",
            score_components={
                "institutional_score": 0.60,
                "liquidity_score": 0.55,
                "catalyst_score": 0.50,
                "momentum_score": 0.50,
            },
        ),
    }


@pytest.fixture
def sample_rejections():
    """Create sample rejection records for testing."""
    return {
        "PENNY": RejectionRecord(
            ticker="PENNY",
            reason=RejectionReason.LIQUIDITY_GATE,
            details="Price $0.50 below minimum $1.00",
            as_of_date="2024-01-15",
        ),
    }


class TestReportConfig:
    """Tests for ReportConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ReportConfig()
        assert config.scores_filename == "alpha_scores.json"
        assert config.report_filename == "ALPHA_ENGINE_REPORT.txt"
        assert config.audit_filename == "audit_log.jsonl"
        assert config.top_n_scores == 20

    def test_custom_config(self, temp_dir):
        """Test custom configuration."""
        config = ReportConfig(
            output_dir=temp_dir,
            top_n_scores=10,
        )
        assert config.output_dir == temp_dir
        assert config.top_n_scores == 10


class TestScoreReporter:
    """Tests for ScoreReporter."""

    def test_write_scores_json(self, temp_dir, sample_score_cards):
        """Test writing scores to JSON."""
        config = ReportConfig(output_dir=temp_dir)
        reporter = ScoreReporter(config)

        output_path = reporter.write_scores_json(sample_score_cards)

        assert os.path.exists(output_path)
        with open(output_path) as f:
            data = json.load(f)
        assert len(data) == 3
        # Should be sorted by ticker
        assert data[0]["ticker"] == "GILD"
        assert data[1]["ticker"] == "MRNA"
        assert data[2]["ticker"] == "VRTX"

    def test_generate_human_report(self, sample_score_cards, sample_rejections):
        """Test generating human-readable report."""
        reporter = ScoreReporter()

        report = reporter.generate_human_report(
            sample_score_cards,
            sample_rejections,
            as_of_date="2024-01-15",
            run_id="test_run",
        )

        assert "ALPHA ENGINE REPORT" in report
        assert "2024-01-15" in report
        assert "MRNA" in report
        assert "GILD" in report
        assert "PENNY" in report  # Rejection
        assert "RISK_CONCENTRATION" in report

    def test_write_human_report(self, temp_dir, sample_score_cards, sample_rejections):
        """Test writing human report to file."""
        config = ReportConfig(output_dir=temp_dir)
        reporter = ScoreReporter(config)

        output_path = reporter.write_human_report(
            sample_score_cards,
            sample_rejections,
            as_of_date="2024-01-15",
            run_id="test_run",
        )

        assert os.path.exists(output_path)
        with open(output_path) as f:
            content = f.read()
        assert "ALPHA ENGINE REPORT" in content

    def test_human_report_shows_top_scores(self, sample_score_cards, sample_rejections):
        """Test that human report shows top scores sorted correctly."""
        reporter = ScoreReporter()

        report = reporter.generate_human_report(
            sample_score_cards,
            sample_rejections,
            as_of_date="2024-01-15",
            run_id="test_run",
        )

        # MRNA (0.75) should appear before GILD (0.65)
        mrna_pos = report.find("MRNA")
        gild_pos = report.find("GILD")
        assert mrna_pos < gild_pos

    def test_human_report_shows_unknown_flags(self, sample_score_cards, sample_rejections):
        """Test that human report flags unknown data."""
        reporter = ScoreReporter()

        report = reporter.generate_human_report(
            sample_score_cards,
            sample_rejections,
            as_of_date="2024-01-15",
            run_id="test_run",
        )

        # GILD has SCORED_PARTIAL status
        assert "SCORED_PARTIAL" in report


class TestAuditLogger:
    """Tests for AuditLogger."""

    def test_create_audit_record(self):
        """Test creating audit record."""
        logger = AuditLogger()

        record = logger.create_audit_record(
            run_id="run_001",
            as_of_date="2024-01-15",
            score_version="1.0.0",
            parameters_hash="b" * 64,
            input_hashes={"market": "hash1", "institutional": "hash2"},
            output_hashes={"scores": "hash3"},
        )

        assert record.run_id == "run_001"
        assert record.pipeline_version == PIPELINE_VERSION
        assert record.status == "COMPLETED"
        assert record.input_hashes["market"] == "hash1"

    def test_append_audit_record(self, temp_dir):
        """Test appending audit record to log."""
        config = ReportConfig(output_dir=temp_dir)
        logger = AuditLogger(config)

        record = logger.create_audit_record(
            run_id="run_001",
            as_of_date="2024-01-15",
            score_version="1.0.0",
            parameters_hash="c" * 64,
            input_hashes={},
            output_hashes={},
        )

        output_path = logger.append_audit_record(record)

        assert os.path.exists(output_path)
        with open(output_path) as f:
            line = f.readline()
        data = json.loads(line)
        assert data["run_id"] == "run_001"

    def test_append_multiple_records(self, temp_dir):
        """Test appending multiple audit records."""
        config = ReportConfig(output_dir=temp_dir)
        logger = AuditLogger(config)

        for i in range(3):
            record = logger.create_audit_record(
                run_id=f"run_{i:03d}",
                as_of_date="2024-01-15",
                score_version="1.0.0",
                parameters_hash="d" * 64,
                input_hashes={},
                output_hashes={},
            )
            logger.append_audit_record(record)

        # Read and verify
        records = logger.read_audit_log()
        assert len(records) == 3
        assert records[0].run_id == "run_000"
        assert records[2].run_id == "run_002"

    def test_read_empty_log(self, temp_dir):
        """Test reading empty/nonexistent log."""
        config = ReportConfig(output_dir=temp_dir)
        logger = AuditLogger(config)

        records = logger.read_audit_log()
        assert records == []


class TestComputeOutputHashes:
    """Tests for compute_output_hashes."""

    def test_compute_hashes(self, sample_score_cards, sample_rejections):
        """Test computing output hashes."""
        hashes = compute_output_hashes(sample_score_cards, sample_rejections)

        assert "scores_hash" in hashes
        assert "rejections_hash" in hashes
        assert len(hashes["scores_hash"]) == 64
        assert len(hashes["rejections_hash"]) == 64

    def test_hashes_deterministic(self, sample_score_cards, sample_rejections):
        """Test that hashes are deterministic."""
        hashes1 = compute_output_hashes(sample_score_cards, sample_rejections)
        hashes2 = compute_output_hashes(sample_score_cards, sample_rejections)

        assert hashes1["scores_hash"] == hashes2["scores_hash"]
        assert hashes1["rejections_hash"] == hashes2["rejections_hash"]


class TestReportingPipeline:
    """Tests for ReportingPipeline."""

    def test_generate_all_reports(self, temp_dir, sample_score_cards, sample_rejections):
        """Test generating all reports at once."""
        config = ReportConfig(output_dir=temp_dir)
        pipeline = ReportingPipeline(config)

        output_files = pipeline.generate_all_reports(
            score_cards=sample_score_cards,
            rejections=sample_rejections,
            as_of_date="2024-01-15",
            run_id="test_run",
            score_version="1.0.0",
            parameters_hash="e" * 64,
            input_hashes={"test": "hash"},
        )

        assert "scores_json" in output_files
        assert "human_report" in output_files
        assert "audit_log" in output_files

        # Verify all files exist
        assert os.path.exists(output_files["scores_json"])
        assert os.path.exists(output_files["human_report"])
        assert os.path.exists(output_files["audit_log"])

    def test_audit_record_includes_stage_counts(self, temp_dir, sample_score_cards, sample_rejections):
        """Test that audit record includes stage counts."""
        config = ReportConfig(output_dir=temp_dir)
        pipeline = ReportingPipeline(config)

        pipeline.generate_all_reports(
            score_cards=sample_score_cards,
            rejections=sample_rejections,
            as_of_date="2024-01-15",
            run_id="test_run",
            score_version="1.0.0",
            parameters_hash="f" * 64,
            input_hashes={},
        )

        records = pipeline.audit_logger.read_audit_log()
        assert len(records) == 1
        assert records[0].stage_counts["scored"] == 3
        assert records[0].stage_counts["rejected"] == 1
