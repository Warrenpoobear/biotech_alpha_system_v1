"""Tests for Risk Layer - Gates and Penalties."""

import pytest
from alpha_engine.contracts import (
    MarketSnapshot,
    FinancialSnapshot,
    InstitutionalSnapshot,
    ManagerPosition,
    SnapshotBundle,
    FeatureVector,
)
from alpha_engine.contracts.outputs import GateStatus
from alpha_engine.risk import (
    GateThresholds,
    GateChecker,
    PenaltyThresholds,
    PenaltyResult,
    PenaltyCalculator,
)


class TestGateThresholds:
    """Tests for GateThresholds configuration."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = GateThresholds()
        assert thresholds.min_adv_usd == 100_000
        assert thresholds.min_price == 1.0
        assert thresholds.min_market_cap == 50_000_000
        assert thresholds.min_runway_months == 6.0

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = GateThresholds(
            min_adv_usd=500_000,
            min_price=5.0,
            min_market_cap=100_000_000,
            min_runway_months=12.0,
        )
        assert thresholds.min_adv_usd == 500_000
        assert thresholds.min_price == 5.0


class TestGateChecker:
    """Tests for GateChecker."""

    def _make_market_snapshot(
        self,
        ticker: str = "MRNA",
        price: float = None,
        market_cap: float = None,
        adv_usd: float = None,
    ) -> MarketSnapshot:
        return MarketSnapshot(
            ticker=ticker,
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="a" * 64,
            price=price,
            market_cap=market_cap,
            adv_usd=adv_usd,
        )

    def _make_financial_snapshot(
        self,
        ticker: str = "MRNA",
        runway_months: float = None,
    ) -> FinancialSnapshot:
        return FinancialSnapshot(
            ticker=ticker,
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="b" * 64,
            runway_months=runway_months,
        )

    def _make_bundle(
        self,
        ticker: str = "MRNA",
        market: MarketSnapshot = None,
        financial: FinancialSnapshot = None,
    ) -> SnapshotBundle:
        return SnapshotBundle(
            ticker=ticker,
            as_of_date="2024-01-15",
            market=market,
            financial=financial,
        )

    def test_liquidity_gates_all_pass(self):
        """Test liquidity gates pass with sufficient values."""
        market = self._make_market_snapshot(
            price=50.0,
            market_cap=1_000_000_000,
            adv_usd=500_000,
        )
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        results = checker.check_liquidity_gates(bundle)
        assert len(results) == 3
        for r in results:
            assert r.status == GateStatus.PASSED

    def test_liquidity_gates_price_fail(self):
        """Test price gate fails below threshold."""
        market = self._make_market_snapshot(
            price=0.50,  # Below $1 threshold
            market_cap=1_000_000_000,
            adv_usd=500_000,
        )
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        results = checker.check_liquidity_gates(bundle)
        price_result = next(r for r in results if r.gate_name == "liquidity_price")
        assert price_result.status == GateStatus.FAILED
        assert "0.50" in price_result.reason

    def test_liquidity_gates_adv_fail(self):
        """Test ADV gate fails below threshold."""
        market = self._make_market_snapshot(
            price=50.0,
            market_cap=1_000_000_000,
            adv_usd=50_000,  # Below $100k threshold
        )
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        results = checker.check_liquidity_gates(bundle)
        adv_result = next(r for r in results if r.gate_name == "liquidity_adv")
        assert adv_result.status == GateStatus.FAILED

    def test_liquidity_gates_market_cap_fail(self):
        """Test market cap gate fails below threshold."""
        market = self._make_market_snapshot(
            price=50.0,
            market_cap=10_000_000,  # Below $50M threshold
            adv_usd=500_000,
        )
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        results = checker.check_liquidity_gates(bundle)
        mcap_result = next(r for r in results if r.gate_name == "liquidity_market_cap")
        assert mcap_result.status == GateStatus.FAILED

    def test_liquidity_gates_unknown_when_missing(self):
        """Test gates return UNKNOWN when data is missing."""
        market = self._make_market_snapshot(price=50.0)  # No market_cap or adv
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        results = checker.check_liquidity_gates(bundle)
        adv_result = next(r for r in results if r.gate_name == "liquidity_adv")
        mcap_result = next(r for r in results if r.gate_name == "liquidity_market_cap")

        assert adv_result.status == GateStatus.UNKNOWN
        assert mcap_result.status == GateStatus.UNKNOWN

    def test_financial_gate_pass(self):
        """Test runway gate passes with sufficient runway."""
        financial = self._make_financial_snapshot(runway_months=24.0)
        bundle = self._make_bundle(financial=financial)
        checker = GateChecker()

        results = checker.check_financial_gates(bundle)
        assert len(results) == 1
        assert results[0].status == GateStatus.PASSED

    def test_financial_gate_fail(self):
        """Test runway gate fails with insufficient runway."""
        financial = self._make_financial_snapshot(runway_months=3.0)  # Below 6 months
        bundle = self._make_bundle(financial=financial)
        checker = GateChecker()

        results = checker.check_financial_gates(bundle)
        assert results[0].status == GateStatus.FAILED
        assert "3.0" in results[0].reason

    def test_financial_gate_unknown(self):
        """Test runway gate returns UNKNOWN when missing."""
        bundle = self._make_bundle()  # No financial data
        checker = GateChecker()

        results = checker.check_financial_gates(bundle)
        assert results[0].status == GateStatus.UNKNOWN

    def test_integrity_gates_pass(self):
        """Test integrity gates pass with required data."""
        market = self._make_market_snapshot(
            price=50.0,
            market_cap=1_000_000_000,
        )
        bundle = self._make_bundle(market=market)
        checker = GateChecker()  # Default requires price and market_cap

        results = checker.check_integrity_gates(bundle)
        for r in results:
            assert r.status == GateStatus.PASSED

    def test_integrity_gates_fail_missing_price(self):
        """Test integrity gate fails when required price is missing."""
        market = self._make_market_snapshot(market_cap=1_000_000_000)  # No price
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        results = checker.check_integrity_gates(bundle)
        price_result = next(r for r in results if r.gate_name == "integrity_price")
        assert price_result.status == GateStatus.FAILED
        assert "Missing" in price_result.reason

    def test_integrity_gates_configurable(self):
        """Test that integrity requirements are configurable."""
        thresholds = GateThresholds(
            require_price=False,
            require_market_cap=False,
            require_adv=True,
        )
        market = self._make_market_snapshot()  # No data
        bundle = self._make_bundle(market=market)
        checker = GateChecker(thresholds=thresholds)

        results = checker.check_integrity_gates(bundle)
        assert len(results) == 1
        assert results[0].gate_name == "integrity_adv"
        assert results[0].status == GateStatus.FAILED

    def test_check_all_gates_passes(self):
        """Test all gates pass with complete good data."""
        market = self._make_market_snapshot(
            price=50.0,
            market_cap=1_000_000_000,
            adv_usd=500_000,
        )
        financial = self._make_financial_snapshot(runway_months=24.0)
        bundle = self._make_bundle(market=market, financial=financial)
        checker = GateChecker()

        passes, results, reasons = checker.check_all_gates(bundle)
        assert passes is True
        assert len(reasons) == 0

    def test_check_all_gates_fails_with_reasons(self):
        """Test all gates returns failure reasons."""
        market = self._make_market_snapshot(
            price=0.50,  # Fails price gate
            market_cap=10_000_000,  # Fails market cap gate
            adv_usd=500_000,
        )
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        passes, results, reasons = checker.check_all_gates(bundle)
        assert passes is False
        assert len(reasons) >= 2
        assert any("price" in r.lower() for r in reasons)
        assert any("market_cap" in r.lower() for r in reasons)

    def test_create_rejection_record(self):
        """Test rejection record creation."""
        market = self._make_market_snapshot(price=0.50)
        bundle = self._make_bundle(market=market)
        checker = GateChecker()

        _, results, _ = checker.check_all_gates(bundle)
        rejection = checker.create_rejection_record("MRNA", results, "2024-01-15")

        assert rejection is not None
        assert rejection.ticker == "MRNA"
        assert len(rejection.gate_results) > 0

    def test_no_rejection_when_passes(self):
        """Test no rejection record when all gates pass."""
        market = self._make_market_snapshot(
            price=50.0,
            market_cap=1_000_000_000,
            adv_usd=500_000,
        )
        financial = self._make_financial_snapshot(runway_months=24.0)
        bundle = self._make_bundle(market=market, financial=financial)
        checker = GateChecker()

        _, results, _ = checker.check_all_gates(bundle)
        rejection = checker.create_rejection_record("MRNA", results)

        assert rejection is None


class TestPenaltyThresholds:
    """Tests for PenaltyThresholds configuration."""

    def test_default_thresholds(self):
        """Test default penalty thresholds."""
        thresholds = PenaltyThresholds()
        assert thresholds.hhi_penalty_start == 2500
        assert thresholds.hhi_penalty_max == 5000
        assert thresholds.hhi_max_penalty == 0.20

    def test_custom_thresholds(self):
        """Test custom penalty thresholds."""
        thresholds = PenaltyThresholds(
            hhi_penalty_start=3000,
            hhi_max_penalty=0.30,
        )
        assert thresholds.hhi_penalty_start == 3000
        assert thresholds.hhi_max_penalty == 0.30


class TestPenaltyCalculator:
    """Tests for PenaltyCalculator."""

    def _make_institutional_snapshot(
        self,
        ticker: str = "MRNA",
        positions: list = None,
        manager_count: int = 0,
        net_buyers: int = 0,
        net_sellers: int = 0,
        new_positions: int = 0,
    ) -> InstitutionalSnapshot:
        return InstitutionalSnapshot(
            ticker=ticker,
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="c" * 64,
            positions=tuple(positions) if positions else (),
            manager_count=manager_count,
            net_buyers=net_buyers,
            net_sellers=net_sellers,
            new_positions=new_positions,
        )

    def _make_bundle(
        self,
        ticker: str = "MRNA",
        institutional: InstitutionalSnapshot = None,
    ) -> SnapshotBundle:
        return SnapshotBundle(
            ticker=ticker,
            as_of_date="2024-01-15",
            institutional=institutional,
        )

    def test_concentration_penalty_no_data(self):
        """Test concentration penalty with no data returns UNKNOWN."""
        bundle = self._make_bundle()
        calc = PenaltyCalculator()

        result = calc.calculate_concentration_penalty(bundle)
        assert result.penalty_value == 0.0
        assert "UNKNOWN" in result.reason

    def test_concentration_penalty_low_hhi(self):
        """Test no penalty for low HHI."""
        # Create positions that result in low HHI
        positions = [
            ManagerPosition(manager_cik=f"{i:010d}", manager_name=f"M{i}", shares=1000, value_usd=10000.0)
            for i in range(10)  # 10 equal positions = HHI of 1000
        ]
        inst = InstitutionalSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="c" * 64,
            positions=tuple(positions),
            manager_count=10,
            total_institutional_value=100000.0,  # Sum of 10 * 10000
        )
        bundle = self._make_bundle(institutional=inst)
        calc = PenaltyCalculator()

        result = calc.calculate_concentration_penalty(bundle)
        assert result.penalty_value == 0.0
        assert result.reason is None

    def test_concentration_penalty_high_hhi(self):
        """Test penalty for high HHI (concentrated ownership)."""
        # Create highly concentrated positions (one large holder)
        positions = [
            ManagerPosition(manager_cik="0000000001", manager_name="BigHolder", shares=9000, value_usd=90000.0),
            ManagerPosition(manager_cik="0000000002", manager_name="SmallHolder", shares=1000, value_usd=10000.0),
        ]
        inst = InstitutionalSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="c" * 64,
            positions=tuple(positions),
            manager_count=2,
            total_institutional_value=100000.0,  # Sum of positions
        )
        bundle = self._make_bundle(institutional=inst)
        calc = PenaltyCalculator()

        result = calc.calculate_concentration_penalty(bundle)
        # HHI = 90^2 + 10^2 = 8100 + 100 = 8200 (above max)
        assert result.penalty_value > 0
        assert result.penalty_value == 0.20  # Max penalty
        assert "Concentrated" in result.reason

    def test_concentration_penalty_mid_range(self):
        """Test partial penalty for mid-range HHI."""
        # Create positions with moderate concentration
        positions = [
            ManagerPosition(manager_cik="0000000001", manager_name="M1", shares=5000, value_usd=50000.0),
            ManagerPosition(manager_cik="0000000002", manager_name="M2", shares=3000, value_usd=30000.0),
            ManagerPosition(manager_cik="0000000003", manager_name="M3", shares=2000, value_usd=20000.0),
        ]
        # HHI = 50^2 + 30^2 + 20^2 = 2500 + 900 + 400 = 3800 (between start and max)
        inst = InstitutionalSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="c" * 64,
            positions=tuple(positions),
            manager_count=3,
            total_institutional_value=100000.0,  # Sum of positions
        )
        bundle = self._make_bundle(institutional=inst)
        calc = PenaltyCalculator()

        result = calc.calculate_concentration_penalty(bundle)
        assert 0 < result.penalty_value < 0.20  # Partial penalty

    def test_concentration_penalty_from_features(self):
        """Test concentration penalty from pre-computed features."""
        features = FeatureVector(
            ticker="MRNA",
            as_of_date="2024-01-15",
            score_version="v1",
            parameters_hash="d" * 64,
            run_id="test",
            features={"concentration_hhi": 4000.0},  # Between start and max
        )
        bundle = self._make_bundle()
        calc = PenaltyCalculator()

        result = calc.calculate_concentration_penalty(bundle, features)
        assert 0 < result.penalty_value < 0.20

    def test_crowding_penalty_no_data(self):
        """Test crowding penalty with no data returns UNKNOWN."""
        bundle = self._make_bundle()
        calc = PenaltyCalculator()

        result = calc.calculate_crowding_penalty(bundle)
        assert result.penalty_value == 0.0
        assert "UNKNOWN" in result.reason

    def test_crowding_penalty_not_crowded(self):
        """Test no penalty when not crowded."""
        inst = self._make_institutional_snapshot(
            manager_count=10,
            net_buyers=3,
            net_sellers=7,  # Low buyer ratio
            new_positions=1,
        )
        bundle = self._make_bundle(institutional=inst)
        calc = PenaltyCalculator()

        result = calc.calculate_crowding_penalty(bundle)
        assert result.penalty_value == 0.0

    def test_crowding_penalty_crowded(self):
        """Test penalty when crowded trade detected."""
        inst = self._make_institutional_snapshot(
            manager_count=10,
            net_buyers=9,  # 90% buyers
            net_sellers=1,
            new_positions=5,  # High conviction
        )
        bundle = self._make_bundle(institutional=inst)
        calc = PenaltyCalculator()

        result = calc.calculate_crowding_penalty(bundle)
        assert result.penalty_value > 0
        assert "Crowded" in result.reason

    def test_volatility_penalty_stub(self):
        """Test volatility penalty returns UNKNOWN (stub)."""
        bundle = self._make_bundle()
        calc = PenaltyCalculator()

        result = calc.calculate_volatility_penalty(bundle)
        assert result.penalty_value == 0.0
        assert "stub" in result.reason.lower()

    def test_calculate_all_penalties(self):
        """Test calculating all penalties at once."""
        bundle = self._make_bundle()
        calc = PenaltyCalculator()

        total, results = calc.calculate_all_penalties(bundle)
        assert len(results) == 3
        assert total >= 0
        assert all(isinstance(r, PenaltyResult) for r in results)

    def test_total_penalty_capped_at_one(self):
        """Test total penalty is capped at 1.0 (100%)."""
        # Use high penalty thresholds to force a theoretical > 100% penalty
        thresholds = PenaltyThresholds(
            hhi_max_penalty=0.60,
            crowding_max_penalty=0.60,
            vol_max_penalty=0.60,
        )
        calc = PenaltyCalculator(thresholds=thresholds)

        # Create very high HHI situation
        positions = [
            ManagerPosition(manager_cik="0000000001", manager_name="M1", shares=10000, value_usd=100000.0),
        ]
        inst = self._make_institutional_snapshot(
            positions=positions,
            manager_count=1,
            net_buyers=1,
            new_positions=1,
        )
        bundle = self._make_bundle(institutional=inst)

        total, _ = calc.calculate_all_penalties(bundle)
        assert total <= 1.0

    def test_get_risk_flags(self):
        """Test extracting risk flags from penalty results."""
        results = [
            PenaltyResult(name="concentration", penalty_value=0.10, reason="test"),
            PenaltyResult(name="crowding", penalty_value=0.02, reason="test"),  # Below threshold
            PenaltyResult(name="volatility", penalty_value=0.08, reason="test"),
        ]
        calc = PenaltyCalculator()

        flags = calc.get_risk_flags(results, threshold=0.05)
        assert "RISK_CONCENTRATION" in flags
        assert "RISK_VOLATILITY" in flags
        assert "RISK_CROWDING" not in flags

    def test_penalty_result_to_dict(self):
        """Test PenaltyResult serialization."""
        result = PenaltyResult(
            name="concentration",
            penalty_value=0.15,
            reason="High HHI",
            input_value=4500.0,
            threshold=2500.0,
        )

        d = result.to_dict()
        assert d["name"] == "concentration"
        assert d["penalty_value"] == 0.15
        assert d["input_value"] == 4500.0


class TestGatesPenaltiesIntegration:
    """Integration tests for gates and penalties working together."""

    def test_gates_before_penalties_workflow(self):
        """Test typical workflow: gates check then penalties."""
        market = MarketSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="a" * 64,
            price=50.0,
            market_cap=1_000_000_000,
            adv_usd=500_000,
        )
        positions = [
            ManagerPosition(manager_cik=f"{i:010d}", manager_name=f"M{i}", shares=1000, value_usd=10000.0)
            for i in range(5)
        ]
        institutional = InstitutionalSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="b" * 64,
            positions=tuple(positions),
            manager_count=5,
            net_buyers=3,
            net_sellers=2,
        )
        financial = FinancialSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="c" * 64,
            runway_months=24.0,
        )

        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
            market=market,
            financial=financial,
            institutional=institutional,
        )

        # Step 1: Check gates
        gate_checker = GateChecker()
        passes_gates, gate_results, _ = gate_checker.check_all_gates(bundle)

        if passes_gates:
            # Step 2: Calculate penalties (only if gates pass)
            penalty_calc = PenaltyCalculator()
            total_penalty, penalty_results = penalty_calc.calculate_all_penalties(bundle)

            assert total_penalty >= 0
            assert total_penalty <= 1.0
        else:
            pytest.fail("Expected gates to pass")
