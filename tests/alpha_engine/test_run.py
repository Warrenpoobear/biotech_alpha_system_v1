"""Tests for Alpha Engine CLI and Orchestration."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from alpha_engine.run import (
    PipelineConfig,
    PipelineStatus,
    AlphaPipeline,
    generate_run_id,
    load_json_file,
    compute_file_hash,
    parse_args,
    main,
    EXIT_SUCCESS,
    EXIT_INPUT_ERROR,
)


@pytest.fixture
def temp_input_dir():
    """Create a temporary input directory with sample data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_dir = Path(tmpdir) / "input"
        input_dir.mkdir()

        # Create sample market data
        market_data = {
            "data": [
                {"ticker": "MRNA", "price": 95.50, "market_cap": 35000000000, "adv": 500000000},
                {"ticker": "GILD", "price": 72.30, "market_cap": 90000000000, "adv": 300000000},
            ]
        }
        with open(input_dir / "market_data.json", "w") as f:
            json.dump(market_data, f)

        # Create sample holdings data
        holdings_data = {
            "positions": [
                {"ticker": "MRNA", "cik": "001", "manager": "M1", "shares": 1000, "value": 100000},
                {"ticker": "GILD", "cik": "002", "manager": "M2", "shares": 2000, "value": 200000},
            ]
        }
        with open(input_dir / "holdings.json", "w") as f:
            json.dump(holdings_data, f)

        # Create sample financial data
        financial_data = {
            "data": [
                {"ticker": "MRNA", "runway_months": 36, "cash": 5000000000},
            ]
        }
        with open(input_dir / "financial_data.json", "w") as f:
            json.dump(financial_data, f)

        yield input_dir


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_config(self, temp_input_dir):
        """Test default configuration."""
        config = PipelineConfig(
            as_of_date="2024-01-15",
            input_dir=temp_input_dir,
        )
        assert config.holdings_file == "holdings.json"
        assert config.market_data_file == "market_data.json"
        assert config.verbose is False


class TestPipelineStatus:
    """Tests for PipelineStatus."""

    def test_stage_tracking(self):
        """Test stage tracking."""
        status = PipelineStatus(verbose=False)
        status.start_stage("Adapt")
        status.complete_stage("Adapt", {"count": 10})

        assert "Adapt" in status.stages_completed
        assert status.stage_results["Adapt"]["count"] == 10

    def test_error_recording(self):
        """Test error recording."""
        status = PipelineStatus(verbose=False)
        status.error("Test error")

        assert len(status.errors) == 1
        assert "Test error" in status.errors[0]


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_generate_run_id_deterministic(self):
        """Test that run ID generation is deterministic."""
        run_id1 = generate_run_id("2024-01-15", "abc123")
        run_id2 = generate_run_id("2024-01-15", "abc123")
        assert run_id1 == run_id2

    def test_generate_run_id_changes_with_date(self):
        """Test that run ID changes with date."""
        run_id1 = generate_run_id("2024-01-15", "abc123")
        run_id2 = generate_run_id("2024-01-16", "abc123")
        assert run_id1 != run_id2

    def test_load_json_file_success(self, temp_input_dir):
        """Test loading JSON file successfully."""
        data, err = load_json_file(temp_input_dir / "market_data.json")
        assert err is None
        assert data is not None
        assert "data" in data

    def test_load_json_file_not_found(self, temp_input_dir):
        """Test loading nonexistent file."""
        data, err = load_json_file(temp_input_dir / "nonexistent.json")
        assert data is None
        assert "not found" in err.lower()

    def test_compute_file_hash_deterministic(self, temp_input_dir):
        """Test that file hash is deterministic."""
        path = temp_input_dir / "market_data.json"
        hash1 = compute_file_hash(path)
        hash2 = compute_file_hash(path)
        assert hash1 == hash2

    def test_compute_file_hash_nonexistent(self, temp_input_dir):
        """Test hash of nonexistent file."""
        hash_val = compute_file_hash(temp_input_dir / "nonexistent.json")
        assert hash_val is None


class TestAlphaPipeline:
    """Tests for AlphaPipeline."""

    def test_pipeline_full_run(self, temp_input_dir, temp_output_dir):
        """Test full pipeline execution."""
        config = PipelineConfig(
            as_of_date="2024-01-15",
            input_dir=temp_input_dir,
            output_dir=temp_output_dir,
            verbose=False,
        )
        pipeline = AlphaPipeline(config)
        exit_code = pipeline.run()

        assert exit_code == EXIT_SUCCESS
        assert (temp_output_dir / "alpha_scores.json").exists()
        assert (temp_output_dir / "ALPHA_ENGINE_REPORT.txt").exists()
        assert (temp_output_dir / "audit_log.jsonl").exists()

    def test_pipeline_generates_scores(self, temp_input_dir, temp_output_dir):
        """Test that pipeline generates valid scores."""
        config = PipelineConfig(
            as_of_date="2024-01-15",
            input_dir=temp_input_dir,
            output_dir=temp_output_dir,
        )
        pipeline = AlphaPipeline(config)
        pipeline.run()

        with open(temp_output_dir / "alpha_scores.json") as f:
            scores = json.load(f)

        assert len(scores) >= 2  # MRNA and GILD
        assert all("ticker" in s for s in scores)
        assert all("score_total" in s for s in scores)

    def test_pipeline_empty_input(self, temp_output_dir):
        """Test pipeline with empty input directory."""
        with tempfile.TemporaryDirectory() as empty_dir:
            config = PipelineConfig(
                as_of_date="2024-01-15",
                input_dir=Path(empty_dir),
                output_dir=temp_output_dir,
            )
            pipeline = AlphaPipeline(config)
            exit_code = pipeline.run()

            assert exit_code == EXIT_INPUT_ERROR

    def test_pipeline_deterministic(self, temp_input_dir, temp_output_dir):
        """Test that pipeline produces deterministic results."""
        with tempfile.TemporaryDirectory() as output_dir2:
            config1 = PipelineConfig(
                as_of_date="2024-01-15",
                input_dir=temp_input_dir,
                output_dir=temp_output_dir,
            )
            config2 = PipelineConfig(
                as_of_date="2024-01-15",
                input_dir=temp_input_dir,
                output_dir=Path(output_dir2),
            )

            pipeline1 = AlphaPipeline(config1)
            pipeline2 = AlphaPipeline(config2)

            pipeline1.run()
            pipeline2.run()

            with open(temp_output_dir / "alpha_scores.json") as f1:
                scores1 = json.load(f1)
            with open(Path(output_dir2) / "alpha_scores.json") as f2:
                scores2 = json.load(f2)

            # Same scores (by output_hash)
            assert [s["output_hash"] for s in scores1] == [s["output_hash"] for s in scores2]


class TestParseArgs:
    """Tests for argument parsing."""

    def test_required_args(self):
        """Test that required arguments are enforced."""
        with pytest.raises(SystemExit):
            parse_args([])  # Missing required args

    def test_valid_args(self):
        """Test parsing valid arguments."""
        args = parse_args([
            "--as-of-date", "2024-01-15",
            "--input-dir", "/tmp/input",
        ])
        assert args.as_of_date == "2024-01-15"
        assert args.input_dir == Path("/tmp/input")

    def test_optional_args(self):
        """Test optional arguments."""
        args = parse_args([
            "--as-of-date", "2024-01-15",
            "--input-dir", "/tmp/input",
            "--output-dir", "/tmp/output",
            "--verbose",
        ])
        assert args.output_dir == Path("/tmp/output")
        assert args.verbose is True

    def test_custom_file_names(self):
        """Test custom file name arguments."""
        args = parse_args([
            "--as-of-date", "2024-01-15",
            "--input-dir", "/tmp/input",
            "--holdings-file", "custom_holdings.json",
        ])
        assert args.holdings_file == "custom_holdings.json"


class TestMain:
    """Tests for main entry point."""

    def test_main_success(self, temp_input_dir, temp_output_dir):
        """Test successful main execution."""
        exit_code = main([
            "--as-of-date", "2024-01-15",
            "--input-dir", str(temp_input_dir),
            "--output-dir", str(temp_output_dir),
        ])
        assert exit_code == EXIT_SUCCESS

    def test_main_invalid_input_dir(self, temp_output_dir):
        """Test main with invalid input directory."""
        exit_code = main([
            "--as-of-date", "2024-01-15",
            "--input-dir", "/nonexistent/path",
            "--output-dir", str(temp_output_dir),
        ])
        assert exit_code == EXIT_INPUT_ERROR

    def test_main_verbose(self, temp_input_dir, temp_output_dir, capsys):
        """Test verbose output."""
        exit_code = main([
            "--as-of-date", "2024-01-15",
            "--input-dir", str(temp_input_dir),
            "--output-dir", str(temp_output_dir),
            "--verbose",
        ])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Alpha Engine" in captured.out
