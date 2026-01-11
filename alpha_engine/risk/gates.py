"""Risk Gates - Kill-switch checks before scoring.

Gates run BEFORE scoring and determine if a ticker should be rejected.
If gates fail: ScoreCard still exists but score=0 and status="REJECTED" with reasons.

Gate types:
- Liquidity gate: ADV minimum, price minimum, market cap minimum
- Financial gate: Runway minimum
- Integrity gate: Missing critical fields → fail-closed
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from alpha_engine.contracts import (
    SnapshotBundle,
    FeatureVector,
    GateResult,
    RejectionRecord,
)
from alpha_engine.contracts.outputs import GateStatus, RejectionReason


@dataclass(frozen=True)
class GateThresholds:
    """Thresholds for gate checks.

    All monetary values in USD.
    """
    # Liquidity gates
    min_adv_usd: float = 100_000  # Minimum average daily volume
    min_price: float = 1.0  # Minimum stock price
    min_market_cap: float = 50_000_000  # Minimum market cap ($50M)

    # Financial gates
    min_runway_months: float = 6.0  # Minimum cash runway

    # Integrity gates
    require_price: bool = True
    require_market_cap: bool = True
    require_adv: bool = False  # ADV often missing, don't require
    require_runway: bool = False  # Runway often missing for profitable companies


class GateChecker:
    """Runs gate checks on snapshot bundles or feature vectors."""

    def __init__(self, thresholds: Optional[GateThresholds] = None):
        self.thresholds = thresholds or GateThresholds()

    def check_liquidity_gates(
        self,
        bundle: SnapshotBundle,
    ) -> List[GateResult]:
        """Check liquidity gates.

        Returns list of GateResult for each check.
        """
        results = []
        ticker = bundle.ticker.upper()
        market = bundle.market

        # ADV check
        adv_value = market.adv_usd if market else None
        if adv_value is not None:
            status = GateStatus.PASSED if adv_value >= self.thresholds.min_adv_usd else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="liquidity_adv",
                status=status,
                threshold=self.thresholds.min_adv_usd,
                actual_value=adv_value,
                reason=f"ADV ${adv_value:,.0f} vs min ${self.thresholds.min_adv_usd:,.0f}" if status == GateStatus.FAILED else None,
            ))
        else:
            results.append(GateResult(
                ticker=ticker,
                gate_name="liquidity_adv",
                status=GateStatus.UNKNOWN,
                threshold=self.thresholds.min_adv_usd,
                actual_value=None,
                reason="ADV data not available",
            ))

        # Price check
        price_value = market.price if market else None
        if price_value is not None:
            status = GateStatus.PASSED if price_value >= self.thresholds.min_price else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="liquidity_price",
                status=status,
                threshold=self.thresholds.min_price,
                actual_value=price_value,
                reason=f"Price ${price_value:.2f} vs min ${self.thresholds.min_price:.2f}" if status == GateStatus.FAILED else None,
            ))
        else:
            results.append(GateResult(
                ticker=ticker,
                gate_name="liquidity_price",
                status=GateStatus.UNKNOWN,
                threshold=self.thresholds.min_price,
                actual_value=None,
                reason="Price data not available",
            ))

        # Market cap check
        mcap_value = market.market_cap if market else None
        if mcap_value is not None:
            status = GateStatus.PASSED if mcap_value >= self.thresholds.min_market_cap else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="liquidity_market_cap",
                status=status,
                threshold=self.thresholds.min_market_cap,
                actual_value=mcap_value,
                reason=f"Market cap ${mcap_value:,.0f} vs min ${self.thresholds.min_market_cap:,.0f}" if status == GateStatus.FAILED else None,
            ))
        else:
            results.append(GateResult(
                ticker=ticker,
                gate_name="liquidity_market_cap",
                status=GateStatus.UNKNOWN,
                threshold=self.thresholds.min_market_cap,
                actual_value=None,
                reason="Market cap data not available",
            ))

        return results

    def check_financial_gates(
        self,
        bundle: SnapshotBundle,
    ) -> List[GateResult]:
        """Check financial health gates.

        Returns list of GateResult for each check.
        """
        results = []
        ticker = bundle.ticker.upper()
        financial = bundle.financial

        # Runway check
        runway_value = financial.runway_months if financial else None
        if runway_value is not None:
            status = GateStatus.PASSED if runway_value >= self.thresholds.min_runway_months else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="financial_runway",
                status=status,
                threshold=self.thresholds.min_runway_months,
                actual_value=runway_value,
                reason=f"Runway {runway_value:.1f} months vs min {self.thresholds.min_runway_months:.1f}" if status == GateStatus.FAILED else None,
            ))
        else:
            results.append(GateResult(
                ticker=ticker,
                gate_name="financial_runway",
                status=GateStatus.UNKNOWN,
                threshold=self.thresholds.min_runway_months,
                actual_value=None,
                reason="Runway data not available",
            ))

        return results

    def check_integrity_gates(
        self,
        bundle: SnapshotBundle,
    ) -> List[GateResult]:
        """Check data integrity gates.

        Fail-closed if required fields are missing.
        """
        results = []
        ticker = bundle.ticker.upper()
        market = bundle.market

        # Price integrity
        if self.thresholds.require_price:
            has_price = market is not None and market.price is not None
            status = GateStatus.PASSED if has_price else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="integrity_price",
                status=status,
                reason="Missing required price data" if status == GateStatus.FAILED else None,
            ))

        # Market cap integrity
        if self.thresholds.require_market_cap:
            has_mcap = market is not None and market.market_cap is not None
            status = GateStatus.PASSED if has_mcap else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="integrity_market_cap",
                status=status,
                reason="Missing required market cap data" if status == GateStatus.FAILED else None,
            ))

        # ADV integrity
        if self.thresholds.require_adv:
            has_adv = market is not None and market.adv_usd is not None
            status = GateStatus.PASSED if has_adv else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="integrity_adv",
                status=status,
                reason="Missing required ADV data" if status == GateStatus.FAILED else None,
            ))

        # Runway integrity
        if self.thresholds.require_runway:
            financial = bundle.financial
            has_runway = financial is not None and financial.runway_months is not None
            status = GateStatus.PASSED if has_runway else GateStatus.FAILED
            results.append(GateResult(
                ticker=ticker,
                gate_name="integrity_runway",
                status=status,
                reason="Missing required runway data" if status == GateStatus.FAILED else None,
            ))

        return results

    def check_all_gates(
        self,
        bundle: SnapshotBundle,
    ) -> tuple:
        """Run all gate checks.

        Returns:
            Tuple of (passes_all: bool, gate_results: List[GateResult], rejection_reasons: List[str])
        """
        all_results = []
        all_results.extend(self.check_liquidity_gates(bundle))
        all_results.extend(self.check_financial_gates(bundle))
        all_results.extend(self.check_integrity_gates(bundle))

        # Determine if passes all gates
        failed_gates = [r for r in all_results if r.status == GateStatus.FAILED]
        passes_all = len(failed_gates) == 0

        rejection_reasons = []
        for gate in failed_gates:
            reason = f"{gate.gate_name}: {gate.reason}" if gate.reason else gate.gate_name
            rejection_reasons.append(reason)

        return passes_all, all_results, sorted(rejection_reasons)

    def create_rejection_record(
        self,
        ticker: str,
        gate_results: List[GateResult],
        as_of_date: Optional[str] = None,
    ) -> Optional[RejectionRecord]:
        """Create rejection record if any gates failed."""
        failed_gates = [r for r in gate_results if r.status == GateStatus.FAILED]
        if not failed_gates:
            return None

        # Determine primary rejection reason
        reason = RejectionReason.MISSING_DATA
        for gate in failed_gates:
            if "liquidity" in gate.gate_name:
                reason = RejectionReason.LIQUIDITY_GATE
                break
            elif "financial" in gate.gate_name:
                reason = RejectionReason.FINANCIAL_GATE
                break
            elif "integrity" in gate.gate_name:
                reason = RejectionReason.INTEGRITY_GATE
                break

        details = "; ".join(g.reason for g in failed_gates if g.reason)

        return RejectionRecord(
            ticker=ticker.upper(),
            reason=reason,
            gate_results=tuple(gate_results),
            details=details,
            as_of_date=as_of_date,
        )
