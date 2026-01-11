"""Risk Penalties - Non-binary adjustments to scores.

Penalties are applied AFTER gates pass and modify the final score.
Unlike gates (binary pass/fail), penalties are continuous adjustments.

Penalty types:
- Concentration penalty: High HHI indicates concentrated ownership
- Crowding penalty: Too many managers increasing simultaneously
- Volatility penalty: (stub - requires vol features)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from alpha_engine.contracts import (
    SnapshotBundle,
    FeatureVector,
)


@dataclass(frozen=True)
class PenaltyThresholds:
    """Thresholds for penalty calculations."""

    # Concentration penalty thresholds
    hhi_penalty_start: float = 2500  # Start penalizing above this HHI
    hhi_penalty_max: float = 5000    # Maximum penalty at this HHI
    hhi_max_penalty: float = 0.20    # Maximum penalty (20%)

    # Crowding penalty thresholds
    crowding_buyer_ratio_high: float = 0.80  # High buyer ratio threshold
    crowding_conviction_high: float = 0.50   # High conviction proxy threshold
    crowding_max_penalty: float = 0.15       # Maximum penalty (15%)

    # Volatility penalty thresholds (stub)
    vol_high_threshold: float = 0.50  # High volatility threshold
    vol_max_penalty: float = 0.10     # Maximum penalty (10%)


@dataclass
class PenaltyResult:
    """Result of a penalty calculation."""
    name: str
    penalty_value: float  # 0.0 to max_penalty, higher = worse
    reason: Optional[str] = None
    input_value: Optional[float] = None
    threshold: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "penalty_value": float(self.penalty_value),
            "reason": self.reason,
            "input_value": float(self.input_value) if self.input_value is not None else None,
            "threshold": float(self.threshold) if self.threshold is not None else None,
        }


class PenaltyCalculator:
    """Calculates risk penalties for scored tickers."""

    def __init__(self, thresholds: Optional[PenaltyThresholds] = None):
        self.thresholds = thresholds or PenaltyThresholds()

    def calculate_concentration_penalty(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> PenaltyResult:
        """Calculate concentration penalty based on HHI.

        Higher HHI = more concentrated ownership = higher penalty.
        Penalty is linear from hhi_penalty_start to hhi_penalty_max.
        """
        hhi = None

        # Try to get HHI from features first
        if features and "concentration_hhi" in features.features:
            hhi = features.features["concentration_hhi"]

        # Calculate from bundle if not in features
        if hhi is None and bundle.institutional and bundle.institutional.positions:
            total_value = bundle.institutional.total_institutional_value
            if total_value and total_value > 0:
                hhi = 0.0
                for pos in bundle.institutional.positions:
                    share = (pos.value_usd / total_value) * 100
                    hhi += share ** 2

        if hhi is None:
            return PenaltyResult(
                name="concentration",
                penalty_value=0.0,
                reason="HHI not available (UNKNOWN)",
                input_value=None,
            )

        # Calculate penalty
        if hhi <= self.thresholds.hhi_penalty_start:
            penalty = 0.0
        elif hhi >= self.thresholds.hhi_penalty_max:
            penalty = self.thresholds.hhi_max_penalty
        else:
            # Linear interpolation
            range_hhi = self.thresholds.hhi_penalty_max - self.thresholds.hhi_penalty_start
            position = (hhi - self.thresholds.hhi_penalty_start) / range_hhi
            penalty = position * self.thresholds.hhi_max_penalty

        reason = None
        if penalty > 0:
            reason = f"Concentrated ownership (HHI={hhi:.0f})"

        return PenaltyResult(
            name="concentration",
            penalty_value=penalty,
            reason=reason,
            input_value=hhi,
            threshold=self.thresholds.hhi_penalty_start,
        )

    def calculate_crowding_penalty(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> PenaltyResult:
        """Calculate crowding penalty.

        Penalty when too many managers are buying simultaneously
        AND conviction proxy is high.
        """
        buyer_ratio = None
        conviction = None

        # Get from features if available
        if features:
            buyer_ratio = features.features.get("institutional_buyer_ratio")
            conviction = features.features.get("conviction_proxy")

        # Calculate from bundle if not in features
        if buyer_ratio is None and bundle.institutional:
            inst = bundle.institutional
            total_active = inst.net_buyers + inst.net_sellers
            if total_active > 0:
                buyer_ratio = inst.net_buyers / total_active
            else:
                buyer_ratio = 0.5

        if conviction is None and bundle.institutional:
            inst = bundle.institutional
            if inst.manager_count > 0:
                conviction = (inst.new_positions + inst.net_buyers) / inst.manager_count

        if buyer_ratio is None or conviction is None:
            return PenaltyResult(
                name="crowding",
                penalty_value=0.0,
                reason="Crowding metrics not available (UNKNOWN)",
                input_value=None,
            )

        # Calculate penalty
        # Only penalize if BOTH buyer ratio AND conviction are high
        penalty = 0.0
        if buyer_ratio >= self.thresholds.crowding_buyer_ratio_high:
            if conviction >= self.thresholds.crowding_conviction_high:
                # Scale penalty based on how extreme both metrics are
                buyer_excess = (buyer_ratio - self.thresholds.crowding_buyer_ratio_high) / (1.0 - self.thresholds.crowding_buyer_ratio_high)
                conviction_excess = (conviction - self.thresholds.crowding_conviction_high) / (1.0 - self.thresholds.crowding_conviction_high)
                # Geometric mean of excesses
                combined = (buyer_excess * conviction_excess) ** 0.5
                penalty = combined * self.thresholds.crowding_max_penalty

        reason = None
        if penalty > 0:
            reason = f"Crowded trade (buyer_ratio={buyer_ratio:.2f}, conviction={conviction:.2f})"

        return PenaltyResult(
            name="crowding",
            penalty_value=penalty,
            reason=reason,
            input_value=buyer_ratio,
            threshold=self.thresholds.crowding_buyer_ratio_high,
        )

    def calculate_volatility_penalty(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> PenaltyResult:
        """Calculate volatility penalty (stub).

        This is a stub - returns UNKNOWN until volatility features are wired.
        """
        vol = None

        # Would get from features if available
        if features:
            vol = features.features.get("volatility")

        if vol is None:
            return PenaltyResult(
                name="volatility",
                penalty_value=0.0,
                reason="Volatility not available (UNKNOWN - stub)",
                input_value=None,
            )

        # Calculate penalty (not reached in stub)
        penalty = 0.0
        if vol > self.thresholds.vol_high_threshold:
            excess = (vol - self.thresholds.vol_high_threshold) / (1.0 - self.thresholds.vol_high_threshold)
            penalty = min(excess, 1.0) * self.thresholds.vol_max_penalty

        reason = None
        if penalty > 0:
            reason = f"High volatility ({vol:.2f})"

        return PenaltyResult(
            name="volatility",
            penalty_value=penalty,
            reason=reason,
            input_value=vol,
            threshold=self.thresholds.vol_high_threshold,
        )

    def calculate_all_penalties(
        self,
        bundle: SnapshotBundle,
        features: Optional[FeatureVector] = None,
    ) -> Tuple[float, List[PenaltyResult]]:
        """Calculate all penalties.

        Returns:
            Tuple of (total_penalty, list of PenaltyResult)
        """
        results = []

        results.append(self.calculate_concentration_penalty(bundle, features))
        results.append(self.calculate_crowding_penalty(bundle, features))
        results.append(self.calculate_volatility_penalty(bundle, features))

        total_penalty = sum(r.penalty_value for r in results)

        # Cap total penalty at 1.0 (100%)
        total_penalty = min(total_penalty, 1.0)

        return total_penalty, results

    def get_risk_flags(
        self,
        penalty_results: List[PenaltyResult],
        threshold: float = 0.05,
    ) -> List[str]:
        """Get risk flags for penalties above threshold.

        Returns list of flag strings.
        """
        flags = []
        for result in penalty_results:
            if result.penalty_value >= threshold:
                flag = f"RISK_{result.name.upper()}"
                flags.append(flag)
        return sorted(flags)
