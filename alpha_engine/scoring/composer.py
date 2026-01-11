"""Score Composer - Blends multiple signal components into final alpha score.

The composer calculates component scores from features/bundles and produces
a final weighted score. All weights are explicitly configured.

Score Components:
- institutional_score: Signal strength from manager activity (mgr_count, net_buyers, conviction)
- liquidity_score: Penalty-adjusted score based on ADV, spread (from gates)
- catalyst_score: Proximity to upcoming catalysts (stub until wired)
- momentum_score: Price/volume momentum signals (stub until wired)

Output: ScoreCard with score_components dict and aggregated score_total.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from alpha_engine.contracts import (
    SnapshotBundle,
    FeatureVector,
    ScoreCard,
    RejectionRecord,
    compute_hash_from_dict,
)
from alpha_engine.contracts.outputs import RejectionReason
from alpha_engine.risk import GateChecker, PenaltyCalculator, GateThresholds, PenaltyThresholds


# Score version for tracking changes to scoring logic
SCORE_VERSION = "1.0.0"


@dataclass(frozen=True)
class ScoringWeights:
    """Weights for combining score components.

    All weights should sum to 1.0 for normalized final score.
    """
    institutional_weight: float = 0.40
    liquidity_weight: float = 0.20
    catalyst_weight: float = 0.20
    momentum_weight: float = 0.20

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for hashing."""
        return {
            "institutional_weight": self.institutional_weight,
            "liquidity_weight": self.liquidity_weight,
            "catalyst_weight": self.catalyst_weight,
            "momentum_weight": self.momentum_weight,
        }

    def validate(self) -> None:
        """Validate weights sum to ~1.0."""
        total = (
            self.institutional_weight +
            self.liquidity_weight +
            self.catalyst_weight +
            self.momentum_weight
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


@dataclass(frozen=True)
class ScoringParameters:
    """All configurable parameters for scoring.

    Used to generate parameters_hash for reproducibility.
    """
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    gate_thresholds: GateThresholds = field(default_factory=GateThresholds)
    penalty_thresholds: PenaltyThresholds = field(default_factory=PenaltyThresholds)

    # Institutional scoring parameters
    mgr_count_scale: float = 50.0  # Scale factor for manager count normalization
    net_buyers_min: int = 3  # Minimum net buyers for positive signal
    conviction_threshold: float = 0.30  # High conviction threshold

    # Liquidity scoring parameters
    adv_ideal: float = 10_000_000  # Ideal ADV for full score
    spread_penalty_threshold: float = 50.0  # Spread (bps) above which to penalize

    # Catalyst scoring parameters
    days_to_catalyst_min: int = 14  # Minimum days to avoid event risk
    days_to_catalyst_ideal: int = 60  # Ideal catalyst proximity

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for hashing."""
        return {
            "weights": self.weights.to_dict(),
            "gate_thresholds": {
                "min_adv_usd": self.gate_thresholds.min_adv_usd,
                "min_price": self.gate_thresholds.min_price,
                "min_market_cap": self.gate_thresholds.min_market_cap,
                "min_runway_months": self.gate_thresholds.min_runway_months,
            },
            "penalty_thresholds": {
                "hhi_penalty_start": self.penalty_thresholds.hhi_penalty_start,
                "hhi_max_penalty": self.penalty_thresholds.hhi_max_penalty,
                "crowding_max_penalty": self.penalty_thresholds.crowding_max_penalty,
            },
            "mgr_count_scale": self.mgr_count_scale,
            "net_buyers_min": self.net_buyers_min,
            "conviction_threshold": self.conviction_threshold,
            "adv_ideal": self.adv_ideal,
            "spread_penalty_threshold": self.spread_penalty_threshold,
            "days_to_catalyst_min": self.days_to_catalyst_min,
            "days_to_catalyst_ideal": self.days_to_catalyst_ideal,
        }

    def compute_hash(self) -> str:
        """Compute deterministic hash of all parameters."""
        return compute_hash_from_dict(self.to_dict())


@dataclass
class ComponentScore:
    """Individual component score with metadata."""
    name: str
    value: float  # 0.0 to 1.0, higher = better
    weight: float  # Weight in final score
    is_unknown: bool = False  # True if computed from insufficient data
    reason: Optional[str] = None

    def weighted_value(self) -> float:
        """Get weighted contribution to final score."""
        return self.value * self.weight

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": float(self.value),
            "weight": float(self.weight),
            "is_unknown": self.is_unknown,
            "reason": self.reason,
        }


class ScoreComposer:
    """Composes alpha scores from snapshot bundles and features."""

    def __init__(
        self,
        parameters: Optional[ScoringParameters] = None,
        run_id: Optional[str] = None,
    ):
        self.parameters = parameters or ScoringParameters()
        self.run_id = run_id or "default"
        self.parameters_hash = self.parameters.compute_hash()

        # Initialize risk layer components
        self.gate_checker = GateChecker(self.parameters.gate_thresholds)
        self.penalty_calculator = PenaltyCalculator(self.parameters.penalty_thresholds)

    def calculate_institutional_score(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> ComponentScore:
        """Calculate institutional signal strength score.

        Based on:
        - Manager count (more managers = more validation)
        - Net buyers vs sellers (buying pressure)
        - Conviction proxy (new positions + strong buyers)
        """
        inst = bundle.institutional

        if inst is None:
            return ComponentScore(
                name="institutional_score",
                value=0.5,  # Neutral score when unknown
                weight=self.parameters.weights.institutional_weight,
                is_unknown=True,
                reason="No institutional data available",
            )

        # Get values from features if available, else from bundle
        mgr_count = inst.manager_count
        net_buyers = inst.net_buyers
        net_sellers = inst.net_sellers

        # Calculate conviction proxy
        conviction = 0.0
        if features and "conviction_proxy" in features.features:
            conviction = features.features.get("conviction_proxy", 0.0) or 0.0
        elif mgr_count > 0:
            conviction = (inst.new_positions + net_buyers) / mgr_count

        # Normalize manager count (0-1 scale)
        mgr_score = min(mgr_count / self.parameters.mgr_count_scale, 1.0)

        # Calculate buyer pressure (0-1 scale)
        total_active = net_buyers + net_sellers
        if total_active > 0:
            buyer_ratio = net_buyers / total_active
        else:
            buyer_ratio = 0.5  # Neutral

        # Boost if conviction is high
        conviction_boost = 0.0
        if conviction >= self.parameters.conviction_threshold:
            conviction_boost = 0.1 * (conviction - self.parameters.conviction_threshold) / (1 - self.parameters.conviction_threshold)

        # Combine components
        # 40% manager breadth, 40% buyer pressure, 20% conviction
        raw_score = (mgr_score * 0.4) + (buyer_ratio * 0.4) + (min(conviction, 1.0) * 0.2)
        raw_score = min(raw_score + conviction_boost, 1.0)

        return ComponentScore(
            name="institutional_score",
            value=raw_score,
            weight=self.parameters.weights.institutional_weight,
            is_unknown=False,
            reason=f"mgr={mgr_count}, buyers={net_buyers}, sellers={net_sellers}",
        )

    def calculate_liquidity_score(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> ComponentScore:
        """Calculate liquidity score.

        Based on:
        - ADV (higher = better liquidity)
        - Bid-ask spread (lower = better)
        - Market cap (larger = more liquid)
        """
        market = bundle.market

        if market is None:
            return ComponentScore(
                name="liquidity_score",
                value=0.5,  # Neutral score when unknown
                weight=self.parameters.weights.liquidity_weight,
                is_unknown=True,
                reason="No market data available",
            )

        # ADV component (0-1)
        adv_score = 0.5
        if market.adv_usd is not None and market.adv_usd > 0:
            adv_score = min(market.adv_usd / self.parameters.adv_ideal, 1.0)

        # Spread penalty (0-1, 1 = no penalty)
        spread_factor = 1.0
        if market.spread_bps is not None and market.spread_bps > self.parameters.spread_penalty_threshold:
            excess = market.spread_bps - self.parameters.spread_penalty_threshold
            spread_factor = max(1.0 - (excess / 100.0), 0.5)  # Cap at 50% penalty

        # Market cap boost (small boost for large caps)
        mcap_boost = 0.0
        if market.market_cap is not None and market.market_cap > 1_000_000_000:  # > $1B
            mcap_boost = 0.1

        raw_score = min(adv_score * spread_factor + mcap_boost, 1.0)

        return ComponentScore(
            name="liquidity_score",
            value=raw_score,
            weight=self.parameters.weights.liquidity_weight,
            is_unknown=market.adv_usd is None,
            reason=f"adv={market.adv_usd}, spread={market.spread_bps}",
        )

    def calculate_catalyst_score(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> ComponentScore:
        """Calculate catalyst proximity score.

        Score is higher when catalyst is at ideal distance:
        - Too close (< 14 days): Lower score (event risk)
        - Ideal (30-90 days): Higher score
        - Too far (> 180 days): Lower score (no near-term catalyst)

        Currently a stub if catalyst data not available.
        """
        catalyst = bundle.catalyst

        if catalyst is None or catalyst.days_to_catalyst is None:
            return ComponentScore(
                name="catalyst_score",
                value=0.5,  # Neutral score when unknown
                weight=self.parameters.weights.catalyst_weight,
                is_unknown=True,
                reason="Catalyst data not available (UNKNOWN)",
            )

        days = catalyst.days_to_catalyst

        # Score based on days to catalyst
        if days < self.parameters.days_to_catalyst_min:
            # Too close - event risk
            raw_score = 0.3
            reason = f"Imminent catalyst ({days} days) - event risk"
        elif days <= self.parameters.days_to_catalyst_ideal:
            # Ideal range - score increases as we approach ideal
            position = (days - self.parameters.days_to_catalyst_min) / (self.parameters.days_to_catalyst_ideal - self.parameters.days_to_catalyst_min)
            raw_score = 0.6 + (0.4 * position)
            reason = f"Good catalyst proximity ({days} days)"
        elif days <= 180:
            # Post-ideal - score decreases
            position = (days - self.parameters.days_to_catalyst_ideal) / (180 - self.parameters.days_to_catalyst_ideal)
            raw_score = max(1.0 - (0.5 * position), 0.5)
            reason = f"Moderate catalyst proximity ({days} days)"
        else:
            # Too far
            raw_score = 0.4
            reason = f"Distant catalyst ({days} days)"

        return ComponentScore(
            name="catalyst_score",
            value=raw_score,
            weight=self.parameters.weights.catalyst_weight,
            is_unknown=False,
            reason=reason,
        )

    def calculate_momentum_score(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> ComponentScore:
        """Calculate momentum score (stub).

        When wired, will be based on:
        - Price momentum (20/50/200 day)
        - Volume momentum
        - Relative strength vs sector

        Currently returns UNKNOWN.
        """
        # Check if momentum features are available
        if features:
            momentum = features.features.get("momentum")
            if momentum is not None:
                return ComponentScore(
                    name="momentum_score",
                    value=float(momentum),
                    weight=self.parameters.weights.momentum_weight,
                    is_unknown=False,
                    reason="From pre-computed features",
                )

        return ComponentScore(
            name="momentum_score",
            value=0.5,  # Neutral score
            weight=self.parameters.weights.momentum_weight,
            is_unknown=True,
            reason="Momentum not available (UNKNOWN - stub)",
        )

    def compose_score(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> Tuple[ScoreCard, Optional[RejectionRecord]]:
        """Compose final score from all components.

        Process:
        1. Run gate checks (fail-closed if gates fail)
        2. Calculate all component scores
        3. Calculate penalties
        4. Apply penalties to produce final score

        Returns:
            Tuple of (ScoreCard, Optional[RejectionRecord])
        """
        ticker = bundle.ticker.upper()
        as_of_date = bundle.as_of_date

        # Step 1: Gate checks
        passes_gates, gate_results, rejection_reasons = self.gate_checker.check_all_gates(bundle)

        if not passes_gates:
            # Create rejection record and zero-score card
            rejection = self.gate_checker.create_rejection_record(
                ticker, gate_results, as_of_date
            )

            score_card = ScoreCard(
                ticker=ticker,
                as_of_date=as_of_date,
                score_version=SCORE_VERSION,
                parameters_hash=self.parameters_hash,
                run_id=self.run_id,
                score_total=0.0,
                status="REJECTED",
                score_components={
                    "institutional_score": 0.0,
                    "liquidity_score": 0.0,
                    "catalyst_score": 0.0,
                    "momentum_score": 0.0,
                },
                passes_gates=False,
                gate_results=[g.to_dict() for g in gate_results],
                rejection_reasons=rejection_reasons if rejection_reasons else ["Gate check failed"],
            )

            return score_card.with_output_hash(), rejection

        # Step 2: Calculate component scores
        components = [
            self.calculate_institutional_score(bundle, features),
            self.calculate_liquidity_score(bundle, features),
            self.calculate_catalyst_score(bundle, features),
            self.calculate_momentum_score(bundle, features),
        ]

        # Step 3: Calculate penalties
        total_penalty, penalty_results = self.penalty_calculator.calculate_all_penalties(
            bundle, features
        )

        # Step 4: Calculate final score
        raw_score = sum(c.weighted_value() for c in components)

        # Apply penalty as multiplicative factor (1 - penalty)
        final_score = raw_score * (1.0 - total_penalty)
        final_score = max(min(final_score, 1.0), 0.0)  # Clamp to [0, 1]

        # Determine status
        unknown_count = sum(1 for c in components if c.is_unknown)
        if unknown_count >= 3:
            status = "SCORED_LOW_CONFIDENCE"
        elif unknown_count >= 1:
            status = "SCORED_PARTIAL"
        else:
            status = "SCORED"

        # Build score components dict
        score_components = {c.name: c.value for c in components}
        score_components["penalty_total"] = total_penalty

        # Build risk flags
        risk_flags = self.penalty_calculator.get_risk_flags(penalty_results)

        score_card = ScoreCard(
            ticker=ticker,
            as_of_date=as_of_date,
            score_version=SCORE_VERSION,
            parameters_hash=self.parameters_hash,
            run_id=self.run_id,
            score_total=final_score,
            status=status,
            score_components=score_components,
            passes_gates=True,
            gate_results=[g.to_dict() for g in gate_results],
            risk_flags=list(risk_flags),
        )

        return score_card.with_output_hash(), None

    def score_bundles(
        self,
        bundles: Dict[str, SnapshotBundle],
        features_by_ticker: Optional[Dict[str, FeatureVector]] = None,
    ) -> Tuple[Dict[str, ScoreCard], Dict[str, RejectionRecord]]:
        """Score multiple ticker bundles.

        Returns:
            Tuple of (scored_cards_dict, rejection_records_dict)
        """
        features_by_ticker = features_by_ticker or {}

        scored_cards = {}
        rejections = {}

        # Process in deterministic order (sorted by ticker)
        for ticker in sorted(bundles.keys()):
            bundle = bundles[ticker]
            features = features_by_ticker.get(ticker)

            score_card, rejection = self.compose_score(bundle, features)
            scored_cards[ticker] = score_card

            if rejection is not None:
                rejections[ticker] = rejection

        return scored_cards, rejections


def create_default_composer(run_id: Optional[str] = None) -> ScoreComposer:
    """Create a ScoreComposer with default parameters."""
    return ScoreComposer(run_id=run_id)
