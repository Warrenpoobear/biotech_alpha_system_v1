"""Tests for Alpha Scoring Core - Score Composer."""

import pytest
from alpha_engine.contracts import (
    MarketSnapshot,
    FinancialSnapshot,
    InstitutionalSnapshot,
    ManagerPosition,
    CatalystSnapshot,
    SnapshotBundle,
    FeatureVector,
)
from alpha_engine.scoring import (
    ScoringWeights,
    ScoringParameters,
    ComponentScore,
    ScoreComposer,
    create_default_composer,
    SCORE_VERSION,
)
from alpha_engine.risk import GateThresholds, PenaltyThresholds


class TestScoringWeights:
    """Tests for ScoringWeights."""

    def test_default_weights(self):
        """Test default weights."""
        weights = ScoringWeights()
        assert weights.institutional_weight == 0.40
        assert weights.liquidity_weight == 0.20
        assert weights.catalyst_weight == 0.20
        assert weights.momentum_weight == 0.20

    def test_weights_sum_to_one(self):
        """Test that default weights sum to 1.0."""
        weights = ScoringWeights()
        total = (
            weights.institutional_weight +
            weights.liquidity_weight +
            weights.catalyst_weight +
            weights.momentum_weight
        )
        assert abs(total - 1.0) < 0.001

    def test_validate_valid_weights(self):
        """Test validation passes for valid weights."""
        weights = ScoringWeights()
        weights.validate()  # Should not raise

    def test_validate_invalid_weights(self):
        """Test validation fails for invalid weights."""
        weights = ScoringWeights(
            institutional_weight=0.5,
            liquidity_weight=0.5,
            catalyst_weight=0.5,
            momentum_weight=0.5,
        )
        with pytest.raises(ValueError):
            weights.validate()

    def test_to_dict(self):
        """Test weights serialization."""
        weights = ScoringWeights()
        d = weights.to_dict()
        assert "institutional_weight" in d
        assert d["institutional_weight"] == 0.40


class TestScoringParameters:
    """Tests for ScoringParameters."""

    def test_default_parameters(self):
        """Test default parameters."""
        params = ScoringParameters()
        assert params.mgr_count_scale == 50.0
        assert params.adv_ideal == 10_000_000
        assert params.days_to_catalyst_min == 14

    def test_compute_hash_deterministic(self):
        """Test that hash is deterministic."""
        params1 = ScoringParameters()
        params2 = ScoringParameters()
        assert params1.compute_hash() == params2.compute_hash()

    def test_compute_hash_changes_with_params(self):
        """Test that hash changes when parameters change."""
        params1 = ScoringParameters()
        params2 = ScoringParameters(mgr_count_scale=100.0)
        assert params1.compute_hash() != params2.compute_hash()


class TestComponentScore:
    """Tests for ComponentScore."""

    def test_weighted_value(self):
        """Test weighted value calculation."""
        score = ComponentScore(
            name="test",
            value=0.8,
            weight=0.4,
        )
        assert score.weighted_value() == pytest.approx(0.32)

    def test_to_dict(self):
        """Test serialization."""
        score = ComponentScore(
            name="institutional_score",
            value=0.75,
            weight=0.40,
            is_unknown=False,
            reason="test reason",
        )
        d = score.to_dict()
        assert d["name"] == "institutional_score"
        assert d["value"] == 0.75
        assert d["weight"] == 0.40
        assert d["is_unknown"] is False


class TestScoreComposer:
    """Tests for ScoreComposer."""

    def _make_market_snapshot(
        self,
        ticker: str = "MRNA",
        price: float = 50.0,
        market_cap: float = 1_000_000_000,
        adv_usd: float = 500_000,
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

    def _make_institutional_snapshot(
        self,
        ticker: str = "MRNA",
        manager_count: int = 10,
        net_buyers: int = 6,
        net_sellers: int = 4,
        new_positions: int = 2,
    ) -> InstitutionalSnapshot:
        return InstitutionalSnapshot(
            ticker=ticker,
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="b" * 64,
            manager_count=manager_count,
            net_buyers=net_buyers,
            net_sellers=net_sellers,
            new_positions=new_positions,
        )

    def _make_financial_snapshot(
        self,
        ticker: str = "MRNA",
        runway_months: float = 24.0,
    ) -> FinancialSnapshot:
        return FinancialSnapshot(
            ticker=ticker,
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="c" * 64,
            runway_months=runway_months,
        )

    def _make_catalyst_snapshot(
        self,
        ticker: str = "MRNA",
        days_to_catalyst: int = 45,
    ) -> CatalystSnapshot:
        return CatalystSnapshot(
            ticker=ticker,
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="d" * 64,
            days_to_catalyst=days_to_catalyst,
            next_catalyst_type="PDUFA",
        )

    def _make_full_bundle(
        self,
        ticker: str = "MRNA",
    ) -> SnapshotBundle:
        return SnapshotBundle(
            ticker=ticker,
            as_of_date="2024-01-15",
            market=self._make_market_snapshot(ticker),
            institutional=self._make_institutional_snapshot(ticker),
            financial=self._make_financial_snapshot(ticker),
            catalyst=self._make_catalyst_snapshot(ticker),
        )

    def test_create_default_composer(self):
        """Test creating default composer."""
        composer = create_default_composer()
        assert composer.parameters is not None
        assert composer.parameters_hash is not None

    def test_compose_score_full_data(self):
        """Test scoring with full data."""
        composer = create_default_composer(run_id="test_run")
        bundle = self._make_full_bundle()

        score_card, rejection = composer.compose_score(bundle)

        assert rejection is None
        assert score_card.ticker == "MRNA"
        assert score_card.status in ("SCORED", "SCORED_PARTIAL")
        assert 0 <= score_card.score_total <= 1
        assert "institutional_score" in score_card.score_components
        assert "liquidity_score" in score_card.score_components
        assert "catalyst_score" in score_card.score_components
        assert "momentum_score" in score_card.score_components
        assert score_card.output_hash is not None

    def test_compose_score_rejected_low_price(self):
        """Test that low price triggers rejection."""
        composer = create_default_composer(run_id="test_run")
        market = self._make_market_snapshot(price=0.50)  # Below $1
        bundle = SnapshotBundle(
            ticker="PENNY",
            as_of_date="2024-01-15",
            market=market,
        )

        score_card, rejection = composer.compose_score(bundle)

        assert rejection is not None
        assert score_card.status == "REJECTED"
        assert score_card.score_total == 0.0
        assert score_card.passes_gates is False

    def test_compose_score_rejected_low_market_cap(self):
        """Test that low market cap triggers rejection."""
        composer = create_default_composer(run_id="test_run")
        market = self._make_market_snapshot(market_cap=10_000_000)  # Below $50M
        bundle = SnapshotBundle(
            ticker="SMALL",
            as_of_date="2024-01-15",
            market=market,
        )

        score_card, rejection = composer.compose_score(bundle)

        assert rejection is not None
        assert score_card.status == "REJECTED"

    def test_compose_score_partial_data(self):
        """Test scoring with partial data."""
        composer = create_default_composer(run_id="test_run")
        # Only market data, no institutional/catalyst
        market = self._make_market_snapshot()
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
            market=market,
        )

        score_card, rejection = composer.compose_score(bundle)

        assert rejection is None  # Should still pass gates
        assert score_card.status in ("SCORED_PARTIAL", "SCORED_LOW_CONFIDENCE")

    def test_institutional_score_calculation(self):
        """Test institutional score component."""
        composer = create_default_composer()
        inst = self._make_institutional_snapshot(
            manager_count=20,
            net_buyers=15,
            net_sellers=5,
        )
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
            institutional=inst,
        )

        score = composer.calculate_institutional_score(bundle)

        assert score.name == "institutional_score"
        assert not score.is_unknown
        assert score.value > 0.5  # Should be positive signal

    def test_institutional_score_unknown_no_data(self):
        """Test institutional score unknown when no data."""
        composer = create_default_composer()
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
        )

        score = composer.calculate_institutional_score(bundle)

        assert score.is_unknown
        assert score.value == 0.5  # Neutral

    def test_liquidity_score_calculation(self):
        """Test liquidity score component."""
        composer = create_default_composer()
        market = self._make_market_snapshot(
            adv_usd=5_000_000,
            market_cap=2_000_000_000,
        )
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
            market=market,
        )

        score = composer.calculate_liquidity_score(bundle)

        assert score.name == "liquidity_score"
        assert not score.is_unknown
        assert score.value > 0.5  # Good liquidity

    def test_catalyst_score_ideal_range(self):
        """Test catalyst score in ideal range."""
        composer = create_default_composer()
        catalyst = self._make_catalyst_snapshot(days_to_catalyst=45)
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
            catalyst=catalyst,
        )

        score = composer.calculate_catalyst_score(bundle)

        assert score.name == "catalyst_score"
        assert not score.is_unknown
        assert score.value >= 0.6  # Good range

    def test_catalyst_score_event_risk(self):
        """Test catalyst score with imminent catalyst."""
        composer = create_default_composer()
        catalyst = self._make_catalyst_snapshot(days_to_catalyst=5)  # Too close
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
            catalyst=catalyst,
        )

        score = composer.calculate_catalyst_score(bundle)

        assert score.value < 0.5  # Event risk penalty

    def test_momentum_score_stub(self):
        """Test momentum score returns unknown (stub)."""
        composer = create_default_composer()
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
        )

        score = composer.calculate_momentum_score(bundle)

        assert score.is_unknown
        assert score.value == 0.5  # Neutral

    def test_momentum_score_from_features(self):
        """Test momentum score from pre-computed features."""
        composer = create_default_composer()
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
        )
        features = FeatureVector(
            ticker="MRNA",
            as_of_date="2024-01-15",
            score_version="v1",
            parameters_hash="x" * 64,
            run_id="test",
            features={"momentum": 0.8},
        )

        score = composer.calculate_momentum_score(bundle, features)

        assert not score.is_unknown
        assert score.value == 0.8

    def test_score_bundles_multiple(self):
        """Test scoring multiple bundles."""
        composer = create_default_composer(run_id="batch_test")
        bundles = {
            "MRNA": self._make_full_bundle("MRNA"),
            "GILD": self._make_full_bundle("GILD"),
            "VRTX": self._make_full_bundle("VRTX"),
        }

        scored, rejections = composer.score_bundles(bundles)

        assert len(scored) == 3
        assert "MRNA" in scored
        assert "GILD" in scored
        assert "VRTX" in scored
        assert len(rejections) == 0

    def test_score_bundles_deterministic_order(self):
        """Test that bundle scoring is deterministic."""
        composer = create_default_composer(run_id="order_test")
        bundles = {
            "VRTX": self._make_full_bundle("VRTX"),
            "MRNA": self._make_full_bundle("MRNA"),
            "GILD": self._make_full_bundle("GILD"),
        }

        scored1, _ = composer.score_bundles(bundles)
        scored2, _ = composer.score_bundles(bundles)

        # Same results regardless of dict ordering
        assert scored1["MRNA"].output_hash == scored2["MRNA"].output_hash
        assert scored1["GILD"].output_hash == scored2["GILD"].output_hash

    def test_score_card_has_output_hash(self):
        """Test that score cards have output hash."""
        composer = create_default_composer(run_id="hash_test")
        bundle = self._make_full_bundle()

        score_card, _ = composer.compose_score(bundle)

        assert score_card.output_hash is not None
        assert len(score_card.output_hash) == 64

    def test_score_card_deterministic_hash(self):
        """Test that score card hash is deterministic."""
        composer = create_default_composer(run_id="determinism_test")
        bundle = self._make_full_bundle()

        score_card1, _ = composer.compose_score(bundle)
        score_card2, _ = composer.compose_score(bundle)

        assert score_card1.output_hash == score_card2.output_hash

    def test_parameters_hash_in_output(self):
        """Test that parameters hash is included in output."""
        composer = create_default_composer(run_id="params_test")
        bundle = self._make_full_bundle()

        score_card, _ = composer.compose_score(bundle)

        assert score_card.parameters_hash == composer.parameters_hash
        assert len(score_card.parameters_hash) == 64

    def test_score_version_in_output(self):
        """Test that score version is included in output."""
        composer = create_default_composer()
        bundle = self._make_full_bundle()

        score_card, _ = composer.compose_score(bundle)

        assert score_card.score_version == SCORE_VERSION

    def test_penalties_affect_score(self):
        """Test that penalties reduce the final score."""
        composer = create_default_composer(run_id="penalty_test")

        # Create bundle with high concentration (penalty trigger)
        positions = [
            ManagerPosition(manager_cik="0000000001", manager_name="BigHolder", shares=9000, value_usd=90000.0),
            ManagerPosition(manager_cik="0000000002", manager_name="SmallHolder", shares=1000, value_usd=10000.0),
        ]
        inst = InstitutionalSnapshot(
            ticker="CONC",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="b" * 64,
            positions=tuple(positions),
            manager_count=2,
            net_buyers=2,
            net_sellers=0,
            total_institutional_value=100000.0,
        )
        market = self._make_market_snapshot()
        bundle = SnapshotBundle(
            ticker="CONC",
            as_of_date="2024-01-15",
            market=market,
            institutional=inst,
        )

        score_card, _ = composer.compose_score(bundle)

        # Should have penalty applied
        assert "penalty_total" in score_card.score_components
        assert score_card.score_components["penalty_total"] > 0
