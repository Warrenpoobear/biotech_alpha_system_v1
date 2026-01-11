"""Tests for biotech screener adapter."""

import pytest
from alpha_engine.adapters.biotech_screener import (
    BiotechScreenerAdapter,
    MappingError,
)


class TestBiotechScreenerAdapter:
    """Tests for BiotechScreenerAdapter."""

    def test_adapt_holdings_basic(self):
        """Test basic holdings adaptation."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        holdings_data = {
            "positions": [
                {
                    "ticker": "MRNA",
                    "cik": "0001234567",
                    "manager": "Vanguard Group",
                    "shares": 1000000,
                    "value": 95000000,
                    "change_shares": 50000,
                },
                {
                    "ticker": "MRNA",
                    "cik": "0009876543",
                    "manager": "BlackRock",
                    "shares": 2000000,
                    "value": 190000000,
                    "change_shares": -100000,
                },
            ]
        }

        snapshots, report = adapter.adapt_holdings(holdings_data)

        assert "MRNA" in snapshots
        snap = snapshots["MRNA"]
        assert snap.manager_count == 2
        assert snap.net_buyers == 1
        assert snap.net_sellers == 1
        assert len(snap.positions) == 2

    def test_adapt_holdings_sorted_by_cik(self):
        """Test that positions are sorted by manager CIK."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        holdings_data = {
            "positions": [
                {"ticker": "GILD", "cik": "9999999999", "manager": "Z Manager", "shares": 100, "value": 1000},
                {"ticker": "GILD", "cik": "0000000001", "manager": "A Manager", "shares": 200, "value": 2000},
            ]
        }

        snapshots, _ = adapter.adapt_holdings(holdings_data)
        positions = snapshots["GILD"].positions

        assert positions[0].manager_cik == "0000000001"
        assert positions[1].manager_cik == "9999999999"

    def test_adapt_holdings_aggregates(self):
        """Test that holdings are properly aggregated."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        holdings_data = {
            "positions": [
                {"ticker": "VRTX", "cik": "001", "manager": "M1", "shares": 1000, "value": 100000, "is_new": True},
                {"ticker": "VRTX", "cik": "002", "manager": "M2", "shares": 2000, "value": 200000, "is_closed": True},
            ]
        }

        snapshots, _ = adapter.adapt_holdings(holdings_data)
        snap = snapshots["VRTX"]

        assert snap.total_institutional_shares == 3000
        assert snap.total_institutional_value == 300000
        assert snap.new_positions == 1
        assert snap.closed_positions == 1

    def test_adapt_holdings_missing_required_fails(self):
        """Test that missing required fields raises error."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        # Missing 'cik' which is required
        holdings_data = {
            "positions": [
                {"ticker": "MRNA", "manager": "Test", "shares": 1000, "value": 100000},
            ]
        }

        with pytest.raises(MappingError):
            adapter.adapt_holdings(holdings_data, fail_closed=True)

    def test_adapt_holdings_missing_required_soft(self):
        """Test that missing required fields can be soft-failed."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        holdings_data = {
            "positions": [
                {"ticker": "MRNA", "manager": "Test", "shares": 1000, "value": 100000},  # Missing cik
                {"ticker": "GILD", "cik": "001", "manager": "Test2", "shares": 2000, "value": 200000},
            ]
        }

        snapshots, report = adapter.adapt_holdings(holdings_data, fail_closed=False)

        # Should only have GILD (MRNA was skipped)
        assert "GILD" in snapshots
        assert len(report.missing_required_fields) > 0

    def test_adapt_market_data_basic(self):
        """Test basic market data adaptation."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        market_data = {
            "data": [
                {"ticker": "MRNA", "price": 95.50, "market_cap": 35000000000, "adv": 500000000},
                {"ticker": "GILD", "close": 72.30, "market_cap": 90000000000},  # Uses 'close' as price
            ]
        }

        snapshots, report = adapter.adapt_market_data(market_data)

        assert "MRNA" in snapshots
        assert snapshots["MRNA"].price == 95.50
        assert snapshots["MRNA"].adv_usd == 500000000

        assert "GILD" in snapshots
        assert snapshots["GILD"].price == 72.30

    def test_adapt_market_data_per_ticker_structure(self):
        """Test market data with per-ticker dict structure."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        market_data = {
            "MRNA": {"price": 95.50, "market_cap": 35000000000},
            "GILD": {"price": 72.30, "market_cap": 90000000000},
        }

        snapshots, _ = adapter.adapt_market_data(market_data)

        assert "MRNA" in snapshots
        assert "GILD" in snapshots

    def test_adapt_financial_data_basic(self):
        """Test basic financial data adaptation."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        financial_data = {
            "data": [
                {"ticker": "MRNA", "runway_months": 36.5, "cash": 5000000000},
                {"ticker": "ALNY", "runway": 24.0, "cash_position": 2000000000},  # Alternative names
            ]
        }

        snapshots, _ = adapter.adapt_financial_data(financial_data)

        assert "MRNA" in snapshots
        assert snapshots["MRNA"].runway_months == 36.5
        assert snapshots["MRNA"].cash_position == 5000000000

        assert "ALNY" in snapshots
        assert snapshots["ALNY"].runway_months == 24.0
        assert snapshots["ALNY"].cash_position == 2000000000

    def test_build_snapshot_bundles(self):
        """Test building snapshot bundles from multiple sources."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        holdings_data = {
            "positions": [
                {"ticker": "MRNA", "cik": "001", "manager": "M1", "shares": 1000, "value": 100000},
            ]
        }
        market_data = {
            "data": [{"ticker": "MRNA", "price": 95.50}, {"ticker": "GILD", "price": 72.30}]
        }
        financial_data = {
            "data": [{"ticker": "MRNA", "runway_months": 36}]
        }

        inst_snaps, _ = adapter.adapt_holdings(holdings_data)
        mkt_snaps, _ = adapter.adapt_market_data(market_data)
        fin_snaps, _ = adapter.adapt_financial_data(financial_data)

        bundles = adapter.build_snapshot_bundles(
            institutional=inst_snaps,
            market=mkt_snaps,
            financial=fin_snaps,
        )

        # Should have both MRNA and GILD
        assert "MRNA" in bundles
        assert "GILD" in bundles

        # MRNA should have all three
        mrna = bundles["MRNA"]
        assert mrna.market is not None
        assert mrna.financial is not None
        assert mrna.institutional is not None

        # GILD should only have market
        gild = bundles["GILD"]
        assert gild.market is not None
        assert gild.financial is None
        assert gild.institutional is None

    def test_ticker_uppercased(self):
        """Test that tickers are uppercased."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        market_data = {"data": [{"ticker": "mrna", "price": 95.50}]}

        snapshots, _ = adapter.adapt_market_data(market_data)

        assert "MRNA" in snapshots
        assert snapshots["MRNA"].ticker == "MRNA"

    def test_mapping_report_generated(self):
        """Test that mapping reports are generated."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        market_data = {
            "data": [{"ticker": "MRNA", "price": 95.50, "extra_field": "ignored"}]
        }

        _, report = adapter.adapt_market_data(market_data)

        assert report.source_file == "market_data.json"
        assert len(report.mappings_used) > 0
        assert "extra_field" in report.unmapped_source_fields

    def test_deterministic_output(self):
        """Test that adaptation produces deterministic output."""
        holdings_data = {
            "positions": [
                {"ticker": "GILD", "cik": "002", "manager": "M2", "shares": 2000, "value": 200000},
                {"ticker": "MRNA", "cik": "001", "manager": "M1", "shares": 1000, "value": 100000},
            ]
        }

        adapter1 = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots1, _ = adapter1.adapt_holdings(holdings_data)

        adapter2 = BiotechScreenerAdapter(as_of_date="2024-01-15")
        snapshots2, _ = adapter2.adapt_holdings(holdings_data)

        # Same input should produce same output
        assert snapshots1["MRNA"].to_json() == snapshots2["MRNA"].to_json()
        assert snapshots1["GILD"].to_json() == snapshots2["GILD"].to_json()

    def test_input_hash_computed(self):
        """Test that input hash is computed and included."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        market_data = {"data": [{"ticker": "MRNA", "price": 95.50}]}
        snapshots, _ = adapter.adapt_market_data(market_data)

        assert snapshots["MRNA"].input_hash is not None
        assert len(snapshots["MRNA"].input_hash) == 64

    def test_list_format_holdings(self):
        """Test holdings as a plain list."""
        adapter = BiotechScreenerAdapter(as_of_date="2024-01-15")

        holdings_data = [
            {"ticker": "MRNA", "cik": "001", "manager": "M1", "shares": 1000, "value": 100000},
        ]

        snapshots, _ = adapter.adapt_holdings(holdings_data)
        assert "MRNA" in snapshots
