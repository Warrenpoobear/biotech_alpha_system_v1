"""Unit tests for Agent 4 integration module."""
import pytest
import pandas as pd
from pydantic import ValidationError

from integrate_agent4 import (
    DetectionRecord,
    validate_detections_df,
    map_to_agent4_format,
)


class TestDetectionRecord:
    """Tests for DetectionRecord schema."""

    def test_valid_record_with_score(self):
        record = DetectionRecord(ticker="AAPL", score=0.85)
        assert record.ticker == "AAPL"
        assert record.get_score_value() == 0.85

    def test_valid_record_with_alpha_score(self):
        record = DetectionRecord(ticker="goog", alpha_score=0.75)
        assert record.ticker == "GOOG"  # Uppercased
        assert record.get_score_value() == 0.75

    def test_score_preferred_over_alpha_score(self):
        record = DetectionRecord(ticker="MSFT", score=0.90, alpha_score=0.80)
        assert record.get_score_value() == 0.90

    def test_invalid_ticker_empty(self):
        with pytest.raises(ValidationError):
            DetectionRecord(ticker="", score=0.5)

    def test_invalid_score_out_of_range(self):
        with pytest.raises(ValidationError):
            DetectionRecord(ticker="TEST", score=1.5)  # > 1.0

        with pytest.raises(ValidationError):
            DetectionRecord(ticker="TEST", score=-0.1)  # < 0.0

    def test_no_score_raises_error(self):
        record = DetectionRecord(ticker="TEST")
        with pytest.raises(ValueError, match="must have 'score' or 'alpha_score'"):
            record.get_score_value()

    def test_extra_fields_ignored(self):
        record = DetectionRecord(
            ticker="TEST",
            score=0.5,
            extra_field="ignored",
            another_field=123
        )
        assert record.ticker == "TEST"
        assert record.score == 0.5


class TestValidateDetectionsDf:
    """Tests for DataFrame validation."""

    def test_valid_dataframe(self):
        df = pd.DataFrame({
            "ticker": ["AAPL", "GOOG", "MSFT"],
            "score": [0.85, 0.75, 0.90],
            "signal_id": ["SIG_1", "SIG_2", "SIG_3"]
        })
        records = validate_detections_df(df)
        assert len(records) == 3
        assert records[0].ticker == "AAPL"

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        records = validate_detections_df(df)
        assert records == []

    def test_missing_ticker_column(self):
        df = pd.DataFrame({
            "symbol": ["AAPL"],  # Wrong column name
            "score": [0.85]
        })
        with pytest.raises(ValueError, match="must have 'ticker' column"):
            validate_detections_df(df)

    def test_missing_score_columns(self):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "value": [0.85]  # Neither 'score' nor 'alpha_score'
        })
        with pytest.raises(ValueError, match="must have 'score' or 'alpha_score'"):
            validate_detections_df(df)

    def test_invalid_rows_collected(self):
        df = pd.DataFrame({
            "ticker": ["AAPL", "", "MSFT"],  # Empty ticker in middle
            "score": [0.85, 0.75, 0.90]
        })
        with pytest.raises(ValueError, match="Validation failed"):
            validate_detections_df(df)


class TestMapToAgent4Format:
    """Tests for mapping to Agent 4 format."""

    def test_basic_mapping(self):
        df = pd.DataFrame({
            "ticker": ["AAPL", "GOOG"],
            "score": [0.85, 0.75]
        })
        result = map_to_agent4_format(df, "2024-01-15")

        assert len(result) == 2
        assert result.iloc[0]["security_id"] == "AAPL"
        assert result.iloc[0]["alpha_score"] == 0.85
        assert result.iloc[0]["signal_type"] == "biotech_alpha"
        assert result.iloc[0]["as_of_date"] == "2024-01-15"

    def test_deterministic_signal_id(self):
        df = pd.DataFrame({
            "ticker": ["TEST"],
            "score": [0.5000]
        })

        result1 = map_to_agent4_format(df, "2024-01-15")
        result2 = map_to_agent4_format(df, "2024-01-15")

        # Same inputs should produce same signal ID
        assert result1.iloc[0]["signal_id"] == result2.iloc[0]["signal_id"]

    def test_different_dates_different_ids(self):
        df = pd.DataFrame({
            "ticker": ["TEST"],
            "score": [0.5000]
        })

        result1 = map_to_agent4_format(df, "2024-01-15")
        result2 = map_to_agent4_format(df, "2024-01-16")

        # Different dates should produce different signal IDs
        assert result1.iloc[0]["signal_id"] != result2.iloc[0]["signal_id"]

    def test_alpha_score_column(self):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "alpha_score": [0.90]  # Using alpha_score instead of score
        })
        result = map_to_agent4_format(df, "2024-01-15")
        assert result.iloc[0]["alpha_score"] == 0.90

    def test_components_field(self):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "score": [0.85]
        })
        result = map_to_agent4_format(df, "2024-01-15")

        components = result.iloc[0]["components"]
        assert components["wake_robin_score"] == 0.85
        assert components["signal_source"] == "wake_robin_v1"
        assert components["detection_date"] == "2024-01-15"
