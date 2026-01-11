"""Integration tests for merge compatibility with biotech screener.

These tests demonstrate:
1. Alpha Engine ingests screener-like data and produces score cards
2. Same input produces byte-identical output (determinism test)
3. Report shows UNKNOWN for missing features cleanly
4. Adapter handles typical screener JSON structures
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
from alpha_engine.contracts import (
    SnapshotBundle,
    ScoreCard,
    canonical_json_dumps,
    canonical_json_loads,
)
from alpha_engine.adapters.biotech_screener import BiotechScreenerAdapter
from alpha_engine.features import create_default_registry
from alpha_engine.scoring import ScoreComposer, ScoringParameters, SCORE_VERSION
from alpha_engine.reporting import ReportingPipeline, ReportConfig
from alpha_engine.run import AlphaPipeline, PipelineConfig, main


# ============================================================
# Sample screener-like data fixtures
# ============================================================

@pytest.fixture
def screener_holdings_data() -> Dict[str, Any]:
    """Typical holdings data from biotech screener."""
    return {
        "positions": [
            {
                "ticker": "MRNA",
                "cik": "0001234567",
                "manager": "Vanguard Group",
                "shares": 5000000,
                "value": 475000000,
                "change_shares": 250000,
            },
            {
                "ticker": "MRNA",
                "cik": "0001555555",
                "manager": "BlackRock",
                "shares": 4000000,
                "value": 380000000,
                "change_shares": -100000,
            },
            {
                "ticker": "GILD",
                "cik": "0001234567",
                "manager": "Vanguard Group",
                "shares": 8000000,
                "value": 578400000,
                "change_shares": 500000,
                "is_new": False,
            },
            {
                "ticker": "GILD",
                "cik": "0001999999",
                "manager": "State Street",
                "shares": 3000000,
                "value": 216900000,
                "change_shares": 200000,
                "is_new": True,
            },
            {
                "ticker": "VRTX",
                "cik": "0001234567",
                "manager": "Vanguard Group",
                "shares": 2000000,
                "value": 820000000,
                "change_shares": 100000,
            },
        ]
    }


@pytest.fixture
def screener_market_data() -> Dict[str, Any]:
    """Typical market data from biotech screener."""
    return {
        "data": [
            {"ticker": "MRNA", "price": 95.50, "market_cap": 35000000000, "adv": 500000000},
            {"ticker": "GILD", "price": 72.30, "market_cap": 90000000000, "adv": 300000000},
            {"ticker": "VRTX", "price": 410.00, "market_cap": 105000000000, "adv": 200000000},
            {"ticker": "ALNY", "price": 180.50, "market_cap": 22000000000, "adv": 100000000},
        ]
    }


@pytest.fixture
def screener_financial_data() -> Dict[str, Any]:
    """Typical financial data from biotech screener."""
    return {
        "data": [
            {"ticker": "MRNA", "runway_months": 48, "cash": 8000000000},
            {"ticker": "GILD", "runway_months": None, "cash": 5000000000},  # Profitable, no runway
            {"ticker": "VRTX", "runway_months": None, "cash": 10000000000},
            {"ticker": "ALNY", "runway_months": 30, "cash": 2000000000},
        ]
    }


@pytest.fixture
def temp_dirs():
    """Create temporary input and output directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_dir = Path(tmpdir) / "input"
        output_dir = Path(tmpdir) / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        yield input_dir, output_dir


# ============================================================
# Test 1: Alpha Engine ingests screener data and produces scores
# ============================================================

class TestScreenerIngestion:
    """Tests for ingesting screener-like data."""

    def test_adapter_handles_holdings_format(self, screener_holdings_data):
        """Test that adapter handles typical holdings JSON structure."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots, report = adapter.adapt_holdings(screener_holdings_data)

        assert "MRNA" in snapshots
        assert "GILD" in snapshots
        assert "VRTX" in snapshots

        mrna = snapshots["MRNA"]
        assert mrna.manager_count == 2
        assert mrna.net_buyers >= 0  # At least some activity

    def test_adapter_handles_market_data_format(self, screener_market_data):
        """Test that adapter handles typical market data JSON structure."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots, report = adapter.adapt_market_data(screener_market_data)

        assert len(snapshots) == 4
        assert snapshots["MRNA"].price == 95.50
        assert snapshots["GILD"].market_cap == 90000000000

    def test_adapter_handles_financial_data_format(self, screener_financial_data):
        """Test that adapter handles typical financial data JSON structure."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots, report = adapter.adapt_financial_data(screener_financial_data)

        assert snapshots["MRNA"].runway_months == 48
        assert snapshots["ALNY"].runway_months == 30
        # GILD has no runway (profitable company)
        assert snapshots["GILD"].runway_months is None

    def test_full_bundle_construction(
        self,
        screener_holdings_data,
        screener_market_data,
        screener_financial_data,
    ):
        """Test building complete bundles from screener data."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        inst_snaps, _ = adapter.adapt_holdings(screener_holdings_data)
        mkt_snaps, _ = adapter.adapt_market_data(screener_market_data)
        fin_snaps, _ = adapter.adapt_financial_data(screener_financial_data)

        bundles = adapter.build_snapshot_bundles(
            institutional=inst_snaps,
            market=mkt_snaps,
            financial=fin_snaps,
        )

        # Should have union of all tickers
        assert "MRNA" in bundles
        assert "GILD" in bundles
        assert "VRTX" in bundles
        assert "ALNY" in bundles  # Only has market data

        # MRNA should have all three data types
        assert bundles["MRNA"].market is not None
        assert bundles["MRNA"].institutional is not None
        assert bundles["MRNA"].financial is not None

        # ALNY only has market data
        assert bundles["ALNY"].market is not None
        assert bundles["ALNY"].institutional is None

    def test_scoring_from_screener_data(
        self,
        screener_holdings_data,
        screener_market_data,
        screener_financial_data,
    ):
        """Test end-to-end scoring from screener data."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        inst_snaps, _ = adapter.adapt_holdings(screener_holdings_data)
        mkt_snaps, _ = adapter.adapt_market_data(screener_market_data)
        fin_snaps, _ = adapter.adapt_financial_data(screener_financial_data)

        bundles = adapter.build_snapshot_bundles(
            institutional=inst_snaps,
            market=mkt_snaps,
            financial=fin_snaps,
        )

        # Compute features
        registry = create_default_registry()
        features_by_ticker = {}
        for ticker, bundle in bundles.items():
            features_by_ticker[ticker] = registry.compute_features(
                bundle,
                score_version=SCORE_VERSION,
                parameters_hash="test",
                run_id="test_run",
            )

        # Score bundles
        composer = ScoreComposer(run_id="test_run")
        score_cards, rejections = composer.score_bundles(bundles, features_by_ticker)

        # Should have scores for all tickers
        assert len(score_cards) == 4
        assert all(card.score_total >= 0 for card in score_cards.values())
        assert all(card.score_total <= 1 for card in score_cards.values())


# ============================================================
# Test 2: Determinism - same input produces byte-identical output
# ============================================================

class TestDeterminism:
    """Tests for output determinism."""

    def test_scoring_deterministic(
        self,
        screener_holdings_data,
        screener_market_data,
    ):
        """Test that same input produces identical scores."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        # Run 1
        inst_snaps1, _ = adapter.adapt_holdings(screener_holdings_data)
        mkt_snaps1, _ = adapter.adapt_market_data(screener_market_data)
        bundles1 = adapter.build_snapshot_bundles(
            institutional=inst_snaps1,
            market=mkt_snaps1,
        )

        composer1 = ScoreComposer(run_id="run_001")
        scores1, _ = composer1.score_bundles(bundles1)

        # Run 2 (identical input)
        inst_snaps2, _ = adapter.adapt_holdings(screener_holdings_data)
        mkt_snaps2, _ = adapter.adapt_market_data(screener_market_data)
        bundles2 = adapter.build_snapshot_bundles(
            institutional=inst_snaps2,
            market=mkt_snaps2,
        )

        composer2 = ScoreComposer(run_id="run_001")  # Same run_id
        scores2, _ = composer2.score_bundles(bundles2)

        # Output hashes should be identical
        for ticker in scores1:
            assert scores1[ticker].output_hash == scores2[ticker].output_hash
            assert scores1[ticker].to_json() == scores2[ticker].to_json()

    def test_json_byte_identical(self, screener_market_data):
        """Test that JSON serialization is byte-identical."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots1, _ = adapter.adapt_market_data(screener_market_data)
        snapshots2, _ = adapter.adapt_market_data(screener_market_data)

        for ticker in snapshots1:
            json1 = snapshots1[ticker].to_json()
            json2 = snapshots2[ticker].to_json()
            assert json1 == json2

    def test_feature_computation_deterministic(
        self,
        screener_holdings_data,
        screener_market_data,
    ):
        """Test that feature computation is deterministic."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        inst_snaps, _ = adapter.adapt_holdings(screener_holdings_data)
        mkt_snaps, _ = adapter.adapt_market_data(screener_market_data)
        bundles = adapter.build_snapshot_bundles(
            institutional=inst_snaps,
            market=mkt_snaps,
        )

        registry = create_default_registry()

        # Compute twice
        features1 = registry.compute_features(
            bundles["MRNA"],
            score_version="v1",
            parameters_hash="test",
            run_id="run_001",
        )
        features2 = registry.compute_features(
            bundles["MRNA"],
            score_version="v1",
            parameters_hash="test",
            run_id="run_001",
        )

        assert features1.to_json() == features2.to_json()

    def test_pipeline_output_deterministic(
        self,
        screener_holdings_data,
        screener_market_data,
        screener_financial_data,
        temp_dirs,
    ):
        """Test full pipeline produces deterministic output files."""
        input_dir, output_dir = temp_dirs

        # Write input files
        with open(input_dir / "holdings.json", "w") as f:
            json.dump(screener_holdings_data, f)
        with open(input_dir / "market_data.json", "w") as f:
            json.dump(screener_market_data, f)
        with open(input_dir / "financial_data.json", "w") as f:
            json.dump(screener_financial_data, f)

        # Run pipeline twice
        with tempfile.TemporaryDirectory() as out1, tempfile.TemporaryDirectory() as out2:
            config1 = PipelineConfig(
                as_of_date="2024-01-15",
                input_dir=input_dir,
                output_dir=Path(out1),
            )
            config2 = PipelineConfig(
                as_of_date="2024-01-15",
                input_dir=input_dir,
                output_dir=Path(out2),
            )

            pipeline1 = AlphaPipeline(config1)
            pipeline2 = AlphaPipeline(config2)

            assert pipeline1.run() == 0
            assert pipeline2.run() == 0

            # Compare outputs
            with open(Path(out1) / "alpha_scores.json") as f1:
                scores1 = json.load(f1)
            with open(Path(out2) / "alpha_scores.json") as f2:
                scores2 = json.load(f2)

            assert len(scores1) == len(scores2)
            for s1, s2 in zip(scores1, scores2):
                assert s1["output_hash"] == s2["output_hash"]


# ============================================================
# Test 3: UNKNOWN handling for missing features
# ============================================================

class TestUnknownHandling:
    """Tests for clean handling of missing/unknown data."""

    def test_partial_data_shows_unknown(self, screener_market_data):
        """Test that missing data produces UNKNOWN status."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        # Only market data, no institutional
        mkt_snaps, _ = adapter.adapt_market_data(screener_market_data)
        bundles = adapter.build_snapshot_bundles(market=mkt_snaps)

        composer = ScoreComposer(run_id="test_run")
        scores, _ = composer.score_bundles(bundles)

        # Should be scored but with partial confidence
        for ticker, card in scores.items():
            assert card.status in ("SCORED_PARTIAL", "SCORED_LOW_CONFIDENCE")

    def test_features_show_missing_reason(self, screener_market_data):
        """Test that missing features have clear reason."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        # Only market data
        mkt_snaps, _ = adapter.adapt_market_data(screener_market_data)
        bundles = adapter.build_snapshot_bundles(market=mkt_snaps)

        registry = create_default_registry()
        features = registry.compute_features(
            bundles["MRNA"],
            score_version="v1",
            parameters_hash="test",
            run_id="test_run",
        )

        # Institutional features should be in missing_features
        assert "institutional_mgr_count" in features.missing_features
        assert features.features.get("institutional_mgr_count") is None

    def test_report_shows_unknown_clearly(
        self,
        screener_market_data,
        temp_dirs,
    ):
        """Test that human report clearly shows unknown data."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        # Only market data
        mkt_snaps, _ = adapter.adapt_market_data(screener_market_data)
        bundles = adapter.build_snapshot_bundles(market=mkt_snaps)

        composer = ScoreComposer(run_id="test_run")
        scores, rejections = composer.score_bundles(bundles)

        _, output_dir = temp_dirs
        config = ReportConfig(output_dir=output_dir)
        pipeline = ReportingPipeline(config)

        pipeline.generate_all_reports(
            score_cards=scores,
            rejections=rejections,
            as_of_date="2024-01-15",
            run_id="test_run",
            score_version=SCORE_VERSION,
            parameters_hash="test",
            input_hashes={},
        )

        with open(output_dir / "ALPHA_ENGINE_REPORT.txt") as f:
            report = f.read()

        # Report should mention unknown/partial data
        assert "UNKNOWN" in report or "PARTIAL" in report or "Low Confidence" in report.lower()


# ============================================================
# Test 4: Alternative screener data formats
# ============================================================

class TestAlternativeFormats:
    """Tests for handling alternative data formats."""

    def test_holdings_as_list(self):
        """Test holdings data as plain list (not wrapped in dict)."""
        holdings_data = [
            {"ticker": "MRNA", "cik": "001", "manager": "M1", "shares": 1000, "value": 100000},
            {"ticker": "GILD", "cik": "002", "manager": "M2", "shares": 2000, "value": 200000},
        ]

        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots, _ = adapter.adapt_holdings(holdings_data)

        assert "MRNA" in snapshots
        assert "GILD" in snapshots

    def test_market_data_per_ticker_dict(self):
        """Test market data as dict keyed by ticker."""
        market_data = {
            "MRNA": {"price": 95.50, "market_cap": 35000000000},
            "GILD": {"price": 72.30, "market_cap": 90000000000},
        }

        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots, _ = adapter.adapt_market_data(market_data)

        assert "MRNA" in snapshots
        assert snapshots["MRNA"].price == 95.50

    def test_alternative_field_names(self):
        """Test alternative field names in data."""
        market_data = {
            "data": [
                {"ticker": "MRNA", "close": 95.50, "mktcap": 35000000000},  # Alternative names
            ]
        }

        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots, _ = adapter.adapt_market_data(market_data)

        # Should still work with alternative names
        assert "MRNA" in snapshots

    def test_lowercase_tickers(self):
        """Test that lowercase tickers are handled."""
        market_data = {
            "data": [
                {"ticker": "mrna", "price": 95.50},
                {"ticker": "Gild", "price": 72.30},
            ]
        }

        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots, _ = adapter.adapt_market_data(market_data)

        assert "MRNA" in snapshots
        assert "GILD" in snapshots


# ============================================================
# Test 5: End-to-end pipeline integration
# ============================================================

class TestEndToEndIntegration:
    """End-to-end integration tests."""

    def test_cli_integration(
        self,
        screener_holdings_data,
        screener_market_data,
        screener_financial_data,
        temp_dirs,
    ):
        """Test CLI-level integration."""
        input_dir, output_dir = temp_dirs

        # Write input files
        with open(input_dir / "holdings.json", "w") as f:
            json.dump(screener_holdings_data, f)
        with open(input_dir / "market_data.json", "w") as f:
            json.dump(screener_market_data, f)
        with open(input_dir / "financial_data.json", "w") as f:
            json.dump(screener_financial_data, f)

        # Run CLI
        exit_code = main([
            "--as-of-date", "2024-01-15",
            "--input-dir", str(input_dir),
            "--output-dir", str(output_dir),
        ])

        assert exit_code == 0

        # Verify outputs
        assert (output_dir / "alpha_scores.json").exists()
        assert (output_dir / "ALPHA_ENGINE_REPORT.txt").exists()
        assert (output_dir / "audit_log.jsonl").exists()

        # Verify scores content
        with open(output_dir / "alpha_scores.json") as f:
            scores = json.load(f)

        assert len(scores) >= 4  # At least MRNA, GILD, VRTX, ALNY
        assert all("output_hash" in s for s in scores)
        assert all("score_total" in s for s in scores)

    def test_full_workflow_with_rejections(self, temp_dirs):
        """Test workflow that includes rejections."""
        input_dir, output_dir = temp_dirs

        # Create data that includes a penny stock (should be rejected)
        market_data = {
            "data": [
                {"ticker": "MRNA", "price": 95.50, "market_cap": 35000000000, "adv": 500000000},
                {"ticker": "PENNY", "price": 0.50, "market_cap": 10000000, "adv": 50000},  # Too low
            ]
        }

        with open(input_dir / "market_data.json", "w") as f:
            json.dump(market_data, f)

        exit_code = main([
            "--as-of-date", "2024-01-15",
            "--input-dir", str(input_dir),
            "--output-dir", str(output_dir),
        ])

        assert exit_code == 0

        with open(output_dir / "alpha_scores.json") as f:
            scores = json.load(f)

        # Find PENNY - should be rejected
        penny = next((s for s in scores if s["ticker"] == "PENNY"), None)
        assert penny is not None
        assert penny["status"] == "REJECTED"
        assert penny["score_total"] == 0

    def test_report_readable_format(
        self,
        screener_holdings_data,
        screener_market_data,
        temp_dirs,
    ):
        """Test that human report is readable and well-formatted."""
        input_dir, output_dir = temp_dirs

        with open(input_dir / "holdings.json", "w") as f:
            json.dump(screener_holdings_data, f)
        with open(input_dir / "market_data.json", "w") as f:
            json.dump(screener_market_data, f)

        main([
            "--as-of-date", "2024-01-15",
            "--input-dir", str(input_dir),
            "--output-dir", str(output_dir),
        ])

        with open(output_dir / "ALPHA_ENGINE_REPORT.txt") as f:
            report = f.read()

        # Check report structure
        assert "ALPHA ENGINE REPORT" in report
        assert "SUMMARY" in report
        assert "TOP" in report
        assert "MRNA" in report or "GILD" in report
        assert "END OF REPORT" in report
