"""Unit tests for source data clients."""
import pytest
from datetime import date
from pathlib import Path
import pandas as pd

from src.data.source_clients.market_data_client import (
    MarketDataClient,
    DemoMarketDataClient,
)
from src.data.source_clients.fda_calendar_client import (
    FDACalendarClient,
    DemoFDACalendarClient,
)
from src.agents.agent2a_pos import _load_sponsor_track_record


class TestMarketDataClient:
    """Tests for MarketDataClient."""

    def test_demo_client_returns_data_for_known_tickers(self):
        client = DemoMarketDataClient()
        universe = pd.DataFrame({"ticker": ["MRNA", "GILD", "VRTX"]})
        result = client.fetch_pricing(as_of=date(2024, 6, 1), universe_df=universe)

        assert len(result) == 3
        assert set(result["ticker"].tolist()) == {"MRNA", "GILD", "VRTX"}

    def test_demo_client_includes_required_columns(self):
        client = DemoMarketDataClient()
        universe = pd.DataFrame({"ticker": ["MRNA"]})
        result = client.fetch_pricing(as_of=date(2024, 6, 1), universe_df=universe)

        required_cols = ["ticker", "date", "close", "volume", "shares_outstanding", "market_cap"]
        for col in required_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_demo_client_generates_default_for_unknown_tickers(self):
        client = DemoMarketDataClient()
        universe = pd.DataFrame({"ticker": ["UNKNOWN_TICKER"]})
        result = client.fetch_pricing(as_of=date(2024, 6, 1), universe_df=universe)

        assert len(result) == 1
        assert result.iloc[0]["ticker"] == "UNKNOWN_TICKER"
        assert result.iloc[0]["close"] == 50.0  # Default value

    def test_demo_client_calculates_market_cap(self):
        client = DemoMarketDataClient()
        universe = pd.DataFrame({"ticker": ["MRNA"]})
        result = client.fetch_pricing(as_of=date(2024, 6, 1), universe_df=universe)

        row = result.iloc[0]
        expected_mcap = row["close"] * row["shares_outstanding"]
        assert row["market_cap"] == expected_mcap

    def test_demo_client_empty_universe(self):
        client = DemoMarketDataClient()
        universe = pd.DataFrame({"ticker": []})
        result = client.fetch_pricing(as_of=date(2024, 6, 1), universe_df=universe)

        assert len(result) == 0
        assert "ticker" in result.columns

    def test_live_client_empty_data_dir(self, tmp_path):
        client = MarketDataClient(data_dir=tmp_path)
        universe = pd.DataFrame({"ticker": ["MRNA"]})
        result = client.fetch_pricing(as_of=date(2024, 6, 1), universe_df=universe)

        assert len(result) == 0  # No files to load from

    def test_live_client_loads_from_csv(self, tmp_path):
        # Create a sample pricing file
        pricing_file = tmp_path / "pricing_latest.csv"
        pricing_file.write_text("ticker,close,volume,shares_outstanding\nMRNA,100.0,5000000,400000000\n")

        client = MarketDataClient(data_dir=tmp_path)
        universe = pd.DataFrame({"ticker": ["MRNA"]})
        result = client.fetch_pricing(as_of=date(2024, 6, 1), universe_df=universe)

        assert len(result) == 1
        assert result.iloc[0]["close"] == 100.0


class TestFDACalendarClient:
    """Tests for FDACalendarClient."""

    def test_demo_client_returns_events_for_known_tickers(self):
        client = DemoFDACalendarClient()
        universe = pd.DataFrame({"ticker": ["MRNA", "GILD", "BIIB"]})
        result = client.fetch_events(as_of=date(2024, 1, 1), universe_df=universe)

        assert len(result) >= 3  # At least one event per ticker
        assert "MRNA" in result["ticker"].tolist()

    def test_demo_client_includes_required_columns(self):
        client = DemoFDACalendarClient()
        universe = pd.DataFrame({"ticker": ["MRNA"]})
        result = client.fetch_events(as_of=date(2024, 1, 1), universe_df=universe)

        required_cols = ["ticker", "event_type", "event_date", "status", "event_description"]
        for col in required_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_demo_client_returns_valid_event_types(self):
        client = DemoFDACalendarClient()
        universe = pd.DataFrame({"ticker": ["MRNA", "GILD", "REGN"]})
        result = client.fetch_events(as_of=date(2024, 1, 1), universe_df=universe)

        valid_types = {"PDUFA", "ADCOMM", "SUBMISSION", "APPROVAL", "CRL", "OTHER"}
        for event_type in result["event_type"].tolist():
            assert event_type in valid_types, f"Invalid event type: {event_type}"

    def test_demo_client_empty_universe(self):
        client = DemoFDACalendarClient()
        universe = pd.DataFrame({"ticker": []})
        result = client.fetch_events(as_of=date(2024, 1, 1), universe_df=universe)

        assert len(result) == 0

    def test_demo_client_unknown_ticker(self):
        client = DemoFDACalendarClient()
        universe = pd.DataFrame({"ticker": ["UNKNOWN_TICKER"]})
        result = client.fetch_events(as_of=date(2024, 1, 1), universe_df=universe)

        assert len(result) == 0  # No events for unknown tickers

    def test_live_client_empty_data_dir(self, tmp_path):
        client = FDACalendarClient(data_dir=tmp_path)
        universe = pd.DataFrame({"ticker": ["MRNA"]})
        result = client.fetch_events(as_of=date(2024, 6, 1), universe_df=universe)

        assert len(result) == 0

    def test_live_client_loads_from_csv(self, tmp_path):
        # Create a sample calendar file
        calendar_file = tmp_path / "fda_calendar_2024.csv"
        calendar_file.write_text(
            "ticker,event_type,event_date,status,event_description\n"
            "MRNA,PDUFA,2024-08-15,scheduled,Test drug approval\n"
        )

        client = FDACalendarClient(data_dir=tmp_path)
        universe = pd.DataFrame({"ticker": ["MRNA"]})
        result = client.fetch_events(as_of=date(2024, 6, 1), universe_df=universe)

        assert len(result) == 1
        assert result.iloc[0]["event_type"] == "PDUFA"


class TestSponsorTrackRecord:
    """Tests for sponsor track record loading."""

    def test_load_valid_yaml(self, tmp_path):
        yaml_file = tmp_path / "sponsors.yaml"
        yaml_file.write_text("""
large_cap:
  AMGN:
    name: Amgen Inc.
    score: 0.70
  GILD:
    name: Gilead Sciences
    score: 0.65
mid_cap:
  ALNY:
    name: Alnylam
    score: 0.60
""")
        scores = _load_sponsor_track_record(yaml_file)

        assert scores["AMGN"] == 0.70
        assert scores["GILD"] == 0.65
        assert scores["ALNY"] == 0.60

    def test_load_missing_file(self, tmp_path):
        missing_file = tmp_path / "missing.yaml"
        scores = _load_sponsor_track_record(missing_file)

        assert scores == {}

    def test_load_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        scores = _load_sponsor_track_record(empty_file)

        assert scores == {}

    def test_ticker_case_insensitive(self, tmp_path):
        yaml_file = tmp_path / "sponsors.yaml"
        yaml_file.write_text("""
large_cap:
  amgn:
    score: 0.70
""")
        scores = _load_sponsor_track_record(yaml_file)

        # Keys should be uppercase
        assert "AMGN" in scores
        assert scores["AMGN"] == 0.70

    def test_missing_score_field_ignored(self, tmp_path):
        yaml_file = tmp_path / "sponsors.yaml"
        yaml_file.write_text("""
large_cap:
  AMGN:
    name: Amgen Inc.
    # No score field
  GILD:
    score: 0.65
""")
        scores = _load_sponsor_track_record(yaml_file)

        assert "AMGN" not in scores  # No score field
        assert scores["GILD"] == 0.65
