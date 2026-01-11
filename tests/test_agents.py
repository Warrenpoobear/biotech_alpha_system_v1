"""Unit tests for agent logic."""
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd

from src.determinism.run_id import RunConfig
from src.agents.agent1_science_catalyst import (
    _phase_from_str,
    _load_design_quality_weights,
    _parse_bool_column,
    ScienceCatalystAgent,
)
from src.schemas.common import SuppressionSeverity, SuppressionFlag
from src.agents.agent2a_pos import _map_indication_to_ta, BASE_RATES, POSAgent
from src.agents.agent4_composite_ranker import (
    _clip,
    _safe_float,
    _score_science,
    _score_pos,
    _score_valuation,
    _score_setup,
)
from src.schemas.science_packet import SciencePacket, TrialPhase, Catalyst, CatalystType
from src.schemas.pos_packet import PoSPacket
from src.schemas.rnpv_packet import RNPVPacket
from src.schemas.market_packet import MarketPacket


class TestPhaseFromStr:
    """Tests for _phase_from_str function."""

    def test_phase1(self):
        assert _phase_from_str("Phase1") == TrialPhase.phase1
        assert _phase_from_str("phase1") == TrialPhase.phase1
        assert _phase_from_str("1") == TrialPhase.phase1

    def test_phase2(self):
        assert _phase_from_str("Phase2") == TrialPhase.phase2
        assert _phase_from_str("2") == TrialPhase.phase2

    def test_phase3(self):
        assert _phase_from_str("Phase3") == TrialPhase.phase3
        assert _phase_from_str("3") == TrialPhase.phase3

    def test_pivotal(self):
        assert _phase_from_str("pivotal") == TrialPhase.pivotal
        assert _phase_from_str("Pivotal Study") == TrialPhase.pivotal

    def test_unknown(self):
        assert _phase_from_str("") == TrialPhase.unknown
        assert _phase_from_str("early") == TrialPhase.unknown
        assert _phase_from_str(None) == TrialPhase.unknown


class TestDesignQualityWeights:
    """Tests for design quality weight loading."""

    def test_load_from_file(self, tmp_path):
        weights_file = tmp_path / "weights.yaml"
        weights_file.write_text("""
trial_design:
  randomized: 0.25
  controlled: 0.25
  blinded: 0.20
  powered: 0.10
endpoint:
  overall_survival: 0.35
  progression_free: 0.25
  objective_response: 0.15
""")
        weights = _load_design_quality_weights(weights_file)
        assert weights["trial_design"]["randomized"] == 0.25
        assert weights["endpoint"]["overall_survival"] == 0.35

    def test_fallback_defaults(self, tmp_path):
        missing_file = tmp_path / "missing.yaml"
        weights = _load_design_quality_weights(missing_file)
        assert weights["trial_design"]["randomized"] == 0.20
        assert weights["endpoint"]["overall_survival"] == 0.30


class TestIndicationToTA:
    """Tests for therapeutic area mapping."""

    def test_oncology_mapping(self):
        assert _map_indication_to_ta("Non-small cell lung cancer") == "oncology"
        assert _map_indication_to_ta("Melanoma Stage IV") == "oncology"
        assert _map_indication_to_ta("Solid tumor") == "oncology"
        assert _map_indication_to_ta("Lymphoma") == "oncology"

    def test_neurology_mapping(self):
        assert _map_indication_to_ta("Alzheimer's Disease") == "neurology"
        assert _map_indication_to_ta("Parkinson's Disease") == "neurology"
        assert _map_indication_to_ta("Epilepsy") == "neurology"

    def test_cardio_mapping(self):
        assert _map_indication_to_ta("Heart Failure") == "cardio"
        assert _map_indication_to_ta("Cardiovascular Disease") == "cardio"
        assert _map_indication_to_ta("Stroke prevention") == "cardio"

    def test_rare_disease_mapping(self):
        assert _map_indication_to_ta("Rare genetic disorder") == "rare_disease"
        assert _map_indication_to_ta("Orphan disease") == "rare_disease"

    def test_infectious_mapping(self):
        assert _map_indication_to_ta("HIV infection") == "infectious"
        assert _map_indication_to_ta("COVID-19") == "infectious"
        assert _map_indication_to_ta("Viral hepatitis") == "infectious"

    def test_other_mapping(self):
        assert _map_indication_to_ta("Diabetes Type 2") == "other"
        assert _map_indication_to_ta("Unknown condition") == "other"


class TestClipAndSafeFloat:
    """Tests for utility functions."""

    def test_clip(self):
        assert _clip(0.5, 0.0, 1.0) == 0.5
        assert _clip(-0.5, 0.0, 1.0) == 0.0
        assert _clip(1.5, 0.0, 1.0) == 1.0

    def test_safe_float(self):
        assert _safe_float(1.5) == 1.5
        assert _safe_float("2.5") == 2.5
        assert _safe_float(None) == 0.0
        assert _safe_float(None, 5.0) == 5.0
        assert _safe_float("invalid", 3.0) == 3.0


class TestScoreScience:
    """Tests for science scoring function."""

    def test_score_with_near_catalyst(self):
        """Closer catalysts should score higher."""
        mock_packet = MagicMock(spec=SciencePacket)
        mock_packet.catalyst_horizon_days = 30  # 30 days out
        mock_packet.next_catalyst = MagicMock()
        mock_packet.next_catalyst.impact_tier = 1
        mock_packet.data_quality_score = 0.8

        score = _score_science(mock_packet)
        # Should be high due to near catalyst + high impact tier
        assert score > 70

    def test_score_with_distant_catalyst(self):
        """Distant catalysts should score lower."""
        mock_packet = MagicMock(spec=SciencePacket)
        mock_packet.catalyst_horizon_days = 300  # 300 days out
        mock_packet.next_catalyst = MagicMock()
        mock_packet.next_catalyst.impact_tier = 3
        mock_packet.data_quality_score = 0.5

        score = _score_science(mock_packet)
        # Should be lower due to distant catalyst
        assert score < 60

    def test_score_with_no_catalyst(self):
        """No catalyst should result in penalty."""
        mock_packet = MagicMock(spec=SciencePacket)
        mock_packet.catalyst_horizon_days = None
        mock_packet.next_catalyst = None
        mock_packet.data_quality_score = 0.5

        score = _score_science(mock_packet)
        assert score > 0  # Should still produce a score
        assert score < 50  # But penalized


class TestScorePos:
    """Tests for PoS scoring function."""

    def test_pos_score_scaling(self):
        mock_packet = MagicMock(spec=PoSPacket)

        mock_packet.final_pos = 0.5
        assert _score_pos(mock_packet) == 50.0

        mock_packet.final_pos = 0.8
        assert _score_pos(mock_packet) == 80.0

        mock_packet.final_pos = 1.0
        assert _score_pos(mock_packet) == 100.0

    def test_pos_score_clipping(self):
        mock_packet = MagicMock(spec=PoSPacket)

        mock_packet.final_pos = 1.5  # Over max
        assert _score_pos(mock_packet) == 100.0

        mock_packet.final_pos = -0.5  # Under min
        assert _score_pos(mock_packet) == 0.0


class TestScoreValuation:
    """Tests for valuation scoring function."""

    def test_no_market_cap(self):
        mock_packet = MagicMock(spec=RNPVPacket)
        mock_packet.total_rnpv_usd = 100_000_000
        assert _score_valuation(mock_packet, None) == 40.0
        assert _score_valuation(mock_packet, 0) == 40.0

    def test_low_ratio(self):
        mock_packet = MagicMock(spec=RNPVPacket)
        mock_packet.total_rnpv_usd = 25_000_000  # 0.25 ratio
        score = _score_valuation(mock_packet, 100_000_000)
        assert 29 < score < 31  # ~30

    def test_high_ratio(self):
        mock_packet = MagicMock(spec=RNPVPacket)
        mock_packet.total_rnpv_usd = 200_000_000  # 2.0 ratio
        score = _score_valuation(mock_packet, 100_000_000)
        assert score >= 90


class TestScoreSetup:
    """Tests for setup/liquidity scoring function."""

    def test_low_adv(self):
        mock_packet = MagicMock(spec=MarketPacket)
        mock_packet.adv_usd = 500_000  # $500k
        score = _score_setup(mock_packet)
        assert score < 10

    def test_medium_adv(self):
        mock_packet = MagicMock(spec=MarketPacket)
        mock_packet.adv_usd = 10_000_000  # $10M
        score = _score_setup(mock_packet)
        assert 40 < score < 70

    def test_high_adv(self):
        mock_packet = MagicMock(spec=MarketPacket)
        mock_packet.adv_usd = 100_000_000  # $100M
        score = _score_setup(mock_packet)
        assert score >= 95


class TestBaseRates:
    """Tests for PoS base rate matrix."""

    def test_phase3_higher_than_phase2(self):
        for ta in ["oncology", "neurology", "cardio", "rare_disease", "infectious"]:
            assert BASE_RATES["phase3"][ta] > BASE_RATES["phase2"][ta]

    def test_infectious_higher_than_oncology(self):
        for phase in ["phase1", "phase2", "phase3"]:
            assert BASE_RATES[phase]["infectious"] > BASE_RATES[phase]["oncology"]

    def test_unknown_phase_conservative(self):
        for ta in BASE_RATES["unknown"]:
            assert BASE_RATES["unknown"][ta] <= 0.35


class TestParseBoolColumn:
    """Tests for _parse_bool_column helper function."""

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        assert _parse_bool_column(df, "is_randomized") is None

    def test_missing_column(self):
        df = pd.DataFrame({"other_col": [True]})
        assert _parse_bool_column(df, "is_randomized") is None

    def test_boolean_true(self):
        df = pd.DataFrame({"is_randomized": [True]})
        assert _parse_bool_column(df, "is_randomized") is True

    def test_boolean_false(self):
        df = pd.DataFrame({"is_randomized": [False]})
        assert _parse_bool_column(df, "is_randomized") is False

    def test_string_true_variants(self):
        for val in ["true", "True", "TRUE", "1", "yes", "Yes", "y", "Y"]:
            df = pd.DataFrame({"col": [val]})
            assert _parse_bool_column(df, "col") is True, f"Failed for {val}"

    def test_string_false_variants(self):
        for val in ["false", "False", "FALSE", "0", "no", "No", "n", "N"]:
            df = pd.DataFrame({"col": [val]})
            assert _parse_bool_column(df, "col") is False, f"Failed for {val}"

    def test_unparseable_string(self):
        df = pd.DataFrame({"col": ["maybe"]})
        assert _parse_bool_column(df, "col") is None

    def test_nan_value(self):
        import numpy as np
        df = pd.DataFrame({"col": [np.nan]})
        assert _parse_bool_column(df, "col") is None


class TestSuppressionSeverity:
    """Tests for SuppressionSeverity enum."""

    def test_enum_values(self):
        assert SuppressionSeverity.info.value == "info"
        assert SuppressionSeverity.warn.value == "warn"
        assert SuppressionSeverity.block.value == "block"

    def test_suppression_flag_with_enum(self):
        flag = SuppressionFlag(
            code="missing_data",
            severity=SuppressionSeverity.warn,
            reason="Data not available"
        )
        assert flag.severity == SuppressionSeverity.warn

    def test_suppression_flag_with_string(self):
        # Backward compatibility: string literals should still work
        flag = SuppressionFlag(
            code="missing_data",
            severity="block",
            reason="Critical data missing"
        )
        assert flag.severity == "block"

    def test_default_severity_is_warn(self):
        flag = SuppressionFlag(code="test", reason="test reason")
        assert flag.severity == SuppressionSeverity.warn
