"""Adapter for biotech screener outputs.

Converts existing screener outputs to canonical Alpha Engine snapshots
WITHOUT modifying the screener code.

Supported inputs:
- holdings_snapshots.json: Institutional holdings data
- market_data.json: Market/pricing data
- financial_data.json: Financial health data
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alpha_engine.contracts import (
    MarketSnapshot,
    FinancialSnapshot,
    InstitutionalSnapshot,
    ManagerPosition,
    UniverseSnapshot,
    SnapshotBundle,
    canonical_json_dumps,
    canonical_json_loads,
    compute_sha256,
    compute_hash_from_dict,
)


class AdapterError(Exception):
    """Raised when adapter fails to convert data."""
    pass


class MappingError(AdapterError):
    """Raised when a required field cannot be mapped."""
    pass


@dataclass
class FieldMapping:
    """Mapping from source field to canonical field."""
    source_field: str
    canonical_field: str
    required: bool = False
    transform: Optional[str] = None  # e.g., "uppercase", "float", "int"
    default: Optional[Any] = None


@dataclass
class MappingReport:
    """Report of field mappings used during adaptation."""
    source_file: str
    mappings_used: List[Dict[str, str]] = field(default_factory=list)
    unmapped_source_fields: List[str] = field(default_factory=list)
    missing_required_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "mappings_used": sorted(self.mappings_used, key=lambda x: x.get("canonical", "")),
            "unmapped_source_fields": sorted(self.unmapped_source_fields),
            "missing_required_fields": sorted(self.missing_required_fields),
            "warnings": self.warnings,
        }


class BiotechScreenerAdapter:
    """Adapter for converting biotech screener outputs to Alpha Engine snapshots."""

    # Field mappings for holdings data
    HOLDINGS_MAPPINGS = {
        "ticker": FieldMapping("ticker", "ticker", required=True, transform="uppercase"),
        "cik": FieldMapping("cik", "manager_cik", required=True),
        "manager": FieldMapping("manager", "manager_name", required=True),
        "shares": FieldMapping("shares", "shares", required=True, transform="int"),
        "value": FieldMapping("value", "value_usd", required=True, transform="float"),
        "change_shares": FieldMapping("change_shares", "change_shares", transform="int"),
        "change_pct": FieldMapping("change_pct", "change_pct", transform="float"),
        "filing_date": FieldMapping("filing_date", "filing_date"),
        "is_new": FieldMapping("is_new", "is_new_position", default=False),
        "is_closed": FieldMapping("is_closed", "is_closed_position", default=False),
    }

    # Field mappings for market data
    MARKET_MAPPINGS = {
        "ticker": FieldMapping("ticker", "ticker", required=True, transform="uppercase"),
        "price": FieldMapping("price", "price", transform="float"),
        "close": FieldMapping("close", "price", transform="float"),  # Alternative name
        "market_cap": FieldMapping("market_cap", "market_cap", transform="float"),
        "adv": FieldMapping("adv", "adv_usd", transform="float"),
        "adv_usd": FieldMapping("adv_usd", "adv_usd", transform="float"),
        "volume": FieldMapping("volume", "volume", transform="float"),
        "shares_outstanding": FieldMapping("shares_outstanding", "shares_outstanding", transform="float"),
        "spread_bps": FieldMapping("spread_bps", "spread_bps", transform="float"),
    }

    # Field mappings for financial data
    FINANCIAL_MAPPINGS = {
        "ticker": FieldMapping("ticker", "ticker", required=True, transform="uppercase"),
        "runway_months": FieldMapping("runway_months", "runway_months", transform="float"),
        "runway": FieldMapping("runway", "runway_months", transform="float"),  # Alternative
        "cash": FieldMapping("cash", "cash_position", transform="float"),
        "cash_position": FieldMapping("cash_position", "cash_position", transform="float"),
        "burn_rate": FieldMapping("burn_rate", "burn_rate", transform="float"),
        "debt_to_equity": FieldMapping("debt_to_equity", "debt_to_equity", transform="float"),
        "current_ratio": FieldMapping("current_ratio", "current_ratio", transform="float"),
    }

    def __init__(self, as_of_date: str, source_id: str = "biotech_screener"):
        """Initialize adapter.

        Args:
            as_of_date: Point-in-time date (ISO format)
            source_id: Identifier for the data source
        """
        self.as_of_date = as_of_date
        self.source_id = source_id
        self.mapping_reports: List[MappingReport] = []

    def _apply_transform(self, value: Any, transform: Optional[str]) -> Any:
        """Apply transformation to a value."""
        if value is None:
            return None
        if transform == "uppercase":
            return str(value).upper().strip()
        if transform == "float":
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        if transform == "int":
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return None
        return value

    def _map_fields(
        self,
        source_data: Dict[str, Any],
        mappings: Dict[str, FieldMapping],
        source_file: str,
    ) -> Tuple[Dict[str, Any], MappingReport]:
        """Map source fields to canonical fields.

        Returns:
            Tuple of (mapped_data, mapping_report)
        """
        report = MappingReport(source_file=source_file)
        result = {}

        # Track which source fields were used
        used_source_fields = set()

        for mapping_key, mapping in mappings.items():
            source_field = mapping.source_field
            canonical_field = mapping.canonical_field

            if source_field in source_data:
                raw_value = source_data[source_field]
                transformed = self._apply_transform(raw_value, mapping.transform)
                result[canonical_field] = transformed
                used_source_fields.add(source_field)
                report.mappings_used.append({
                    "source": source_field,
                    "canonical": canonical_field,
                    "transform": mapping.transform,
                })
            elif mapping.default is not None:
                result[canonical_field] = mapping.default
            elif mapping.required:
                report.missing_required_fields.append(source_field)

        # Track unmapped source fields
        for field in source_data.keys():
            if field not in used_source_fields:
                report.unmapped_source_fields.append(field)

        return result, report

    def adapt_holdings(
        self,
        holdings_data: Dict[str, Any],
        fail_closed: bool = True,
    ) -> Tuple[Dict[str, InstitutionalSnapshot], MappingReport]:
        """Adapt holdings_snapshots.json to InstitutionalSnapshots.

        Args:
            holdings_data: Parsed holdings_snapshots.json content
            fail_closed: If True, raise on missing required fields

        Returns:
            Tuple of (dict of ticker -> InstitutionalSnapshot, MappingReport)
        """
        input_hash = compute_hash_from_dict(holdings_data)
        report = MappingReport(source_file="holdings_snapshots.json")

        snapshots: Dict[str, InstitutionalSnapshot] = {}

        # Group positions by ticker
        ticker_positions: Dict[str, List[ManagerPosition]] = {}
        ticker_aggregates: Dict[str, Dict[str, Any]] = {}

        # Handle different possible structures
        positions_list = []
        if isinstance(holdings_data, dict):
            if "positions" in holdings_data:
                positions_list = holdings_data["positions"]
            elif "holdings" in holdings_data:
                positions_list = holdings_data["holdings"]
            elif "data" in holdings_data:
                positions_list = holdings_data["data"]
            else:
                # Try to extract from nested structure
                for key, value in holdings_data.items():
                    if isinstance(value, list):
                        positions_list = value
                        break
        elif isinstance(holdings_data, list):
            positions_list = holdings_data

        for pos_data in positions_list:
            mapped, pos_report = self._map_fields(
                pos_data, self.HOLDINGS_MAPPINGS, "holdings_position"
            )
            report.mappings_used.extend(pos_report.mappings_used)
            report.unmapped_source_fields.extend(pos_report.unmapped_source_fields)

            if pos_report.missing_required_fields:
                report.missing_required_fields.extend(pos_report.missing_required_fields)
                if fail_closed:
                    raise MappingError(
                        f"Missing required fields: {pos_report.missing_required_fields}"
                    )
                continue

            ticker = mapped.get("ticker", "").upper()
            if not ticker:
                continue

            position = ManagerPosition(
                manager_cik=str(mapped.get("manager_cik", "")),
                manager_name=str(mapped.get("manager_name", "")),
                shares=int(mapped.get("shares", 0)),
                value_usd=float(mapped.get("value_usd", 0)),
                change_shares=mapped.get("change_shares"),
                change_pct=mapped.get("change_pct"),
                filing_date=mapped.get("filing_date"),
                is_new_position=bool(mapped.get("is_new_position", False)),
                is_closed_position=bool(mapped.get("is_closed_position", False)),
            )

            if ticker not in ticker_positions:
                ticker_positions[ticker] = []
                ticker_aggregates[ticker] = {
                    "total_shares": 0,
                    "total_value": 0,
                    "net_buyers": 0,
                    "net_sellers": 0,
                    "new_positions": 0,
                    "closed_positions": 0,
                    "net_flow": 0,
                }

            ticker_positions[ticker].append(position)
            agg = ticker_aggregates[ticker]
            agg["total_shares"] += position.shares
            agg["total_value"] += position.value_usd

            if position.change_shares:
                if position.change_shares > 0:
                    agg["net_buyers"] += 1
                    agg["net_flow"] += position.change_shares * (position.value_usd / max(position.shares, 1))
                elif position.change_shares < 0:
                    agg["net_sellers"] += 1
                    agg["net_flow"] += position.change_shares * (position.value_usd / max(position.shares, 1))

            if position.is_new_position:
                agg["new_positions"] += 1
            if position.is_closed_position:
                agg["closed_positions"] += 1

        # Create snapshots
        for ticker in sorted(ticker_positions.keys()):
            positions = tuple(sorted(
                ticker_positions[ticker],
                key=lambda p: p.manager_cik
            ))
            agg = ticker_aggregates[ticker]

            snapshots[ticker] = InstitutionalSnapshot(
                ticker=ticker,
                as_of_date=self.as_of_date,
                source_id=self.source_id,
                input_hash=input_hash,
                total_institutional_shares=agg["total_shares"],
                total_institutional_value=agg["total_value"],
                manager_count=len(positions),
                net_buyers=agg["net_buyers"],
                net_sellers=agg["net_sellers"],
                new_positions=agg["new_positions"],
                closed_positions=agg["closed_positions"],
                net_flow_kusd=agg["net_flow"] / 1000 if agg["net_flow"] else None,
                positions=positions,
            )

        self.mapping_reports.append(report)
        return snapshots, report

    def adapt_market_data(
        self,
        market_data: Dict[str, Any],
        fail_closed: bool = True,
    ) -> Tuple[Dict[str, MarketSnapshot], MappingReport]:
        """Adapt market_data.json to MarketSnapshots.

        Args:
            market_data: Parsed market_data.json content
            fail_closed: If True, raise on missing required fields

        Returns:
            Tuple of (dict of ticker -> MarketSnapshot, MappingReport)
        """
        input_hash = compute_hash_from_dict(market_data)
        report = MappingReport(source_file="market_data.json")

        snapshots: Dict[str, MarketSnapshot] = {}

        # Handle different structures
        data_list = []
        if isinstance(market_data, dict):
            if "data" in market_data:
                data_list = market_data["data"]
            elif "tickers" in market_data:
                data_list = market_data["tickers"]
            else:
                # Try per-ticker structure
                for ticker, ticker_data in market_data.items():
                    if isinstance(ticker_data, dict):
                        ticker_data["ticker"] = ticker
                        data_list.append(ticker_data)
        elif isinstance(market_data, list):
            data_list = market_data

        for item in data_list:
            mapped, item_report = self._map_fields(
                item, self.MARKET_MAPPINGS, "market_data_item"
            )
            report.mappings_used.extend(item_report.mappings_used)
            report.unmapped_source_fields.extend(item_report.unmapped_source_fields)

            if item_report.missing_required_fields:
                report.missing_required_fields.extend(item_report.missing_required_fields)
                if fail_closed:
                    raise MappingError(
                        f"Missing required fields: {item_report.missing_required_fields}"
                    )
                continue

            ticker = mapped.get("ticker", "").upper()
            if not ticker:
                continue

            snapshots[ticker] = MarketSnapshot(
                ticker=ticker,
                as_of_date=self.as_of_date,
                source_id=self.source_id,
                input_hash=input_hash,
                price=mapped.get("price"),
                market_cap=mapped.get("market_cap"),
                adv_usd=mapped.get("adv_usd"),
                volume=mapped.get("volume"),
                shares_outstanding=mapped.get("shares_outstanding"),
                spread_bps=mapped.get("spread_bps"),
            )

        self.mapping_reports.append(report)
        return snapshots, report

    def adapt_financial_data(
        self,
        financial_data: Dict[str, Any],
        fail_closed: bool = True,
    ) -> Tuple[Dict[str, FinancialSnapshot], MappingReport]:
        """Adapt financial_data.json to FinancialSnapshots.

        Args:
            financial_data: Parsed financial_data.json content
            fail_closed: If True, raise on missing required fields

        Returns:
            Tuple of (dict of ticker -> FinancialSnapshot, MappingReport)
        """
        input_hash = compute_hash_from_dict(financial_data)
        report = MappingReport(source_file="financial_data.json")

        snapshots: Dict[str, FinancialSnapshot] = {}

        # Handle different structures
        data_list = []
        if isinstance(financial_data, dict):
            if "data" in financial_data:
                data_list = financial_data["data"]
            elif "tickers" in financial_data:
                data_list = financial_data["tickers"]
            else:
                # Try per-ticker structure
                for ticker, ticker_data in financial_data.items():
                    if isinstance(ticker_data, dict):
                        ticker_data["ticker"] = ticker
                        data_list.append(ticker_data)
        elif isinstance(financial_data, list):
            data_list = financial_data

        for item in data_list:
            mapped, item_report = self._map_fields(
                item, self.FINANCIAL_MAPPINGS, "financial_data_item"
            )
            report.mappings_used.extend(item_report.mappings_used)
            report.unmapped_source_fields.extend(item_report.unmapped_source_fields)

            if item_report.missing_required_fields:
                report.missing_required_fields.extend(item_report.missing_required_fields)
                if fail_closed:
                    raise MappingError(
                        f"Missing required fields: {item_report.missing_required_fields}"
                    )
                continue

            ticker = mapped.get("ticker", "").upper()
            if not ticker:
                continue

            snapshots[ticker] = FinancialSnapshot(
                ticker=ticker,
                as_of_date=self.as_of_date,
                source_id=self.source_id,
                input_hash=input_hash,
                runway_months=mapped.get("runway_months"),
                cash_position=mapped.get("cash_position"),
                burn_rate=mapped.get("burn_rate"),
                debt_to_equity=mapped.get("debt_to_equity"),
                current_ratio=mapped.get("current_ratio"),
            )

        self.mapping_reports.append(report)
        return snapshots, report

    def build_snapshot_bundles(
        self,
        institutional: Optional[Dict[str, InstitutionalSnapshot]] = None,
        market: Optional[Dict[str, MarketSnapshot]] = None,
        financial: Optional[Dict[str, FinancialSnapshot]] = None,
    ) -> Dict[str, SnapshotBundle]:
        """Build snapshot bundles from adapted snapshots.

        Combines all snapshot types into per-ticker bundles.
        """
        # Collect all tickers
        all_tickers = set()
        if institutional:
            all_tickers.update(institutional.keys())
        if market:
            all_tickers.update(market.keys())
        if financial:
            all_tickers.update(financial.keys())

        bundles: Dict[str, SnapshotBundle] = {}
        for ticker in sorted(all_tickers):
            bundles[ticker] = SnapshotBundle(
                ticker=ticker,
                as_of_date=self.as_of_date,
                market=market.get(ticker) if market else None,
                financial=financial.get(ticker) if financial else None,
                institutional=institutional.get(ticker) if institutional else None,
            )

        return bundles

    def get_mapping_reports(self) -> List[Dict[str, Any]]:
        """Get all mapping reports as dictionaries."""
        return [r.to_dict() for r in self.mapping_reports]
