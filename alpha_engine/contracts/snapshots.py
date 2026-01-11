"""Canonical snapshot dataclasses for Alpha Engine inputs.

Every snapshot includes:
- as_of_date: Point-in-time date (ISO format string)
- source_id: Identifier for the data source
- input_hash: SHA256 hash of raw input data
- schema_version: Version of this schema
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .serialization import canonical_json_dumps, compute_hash_from_dict, stable_float


# Current schema versions
MARKET_SNAPSHOT_VERSION = "1.0.0"
FINANCIAL_SNAPSHOT_VERSION = "1.0.0"
INSTITUTIONAL_SNAPSHOT_VERSION = "1.0.0"
CATALYST_SNAPSHOT_VERSION = "1.0.0"
UNIVERSE_SNAPSHOT_VERSION = "1.0.0"


@dataclass(frozen=True)
class MarketSnapshot:
    """Point-in-time market data snapshot for a ticker.

    Fields:
    - ticker: Stock ticker symbol (uppercase)
    - as_of_date: ISO date string (YYYY-MM-DD)
    - source_id: Data source identifier
    - input_hash: SHA256 of raw input
    - schema_version: Schema version string

    Market data:
    - price: Last closing price (USD)
    - market_cap: Market capitalization (USD)
    - adv_usd: Average daily volume in USD
    - spread_bps: Bid-ask spread in basis points (optional)
    - volume: Trading volume (shares)
    - shares_outstanding: Total shares outstanding
    """
    ticker: str
    as_of_date: str
    source_id: str
    input_hash: str
    schema_version: str = MARKET_SNAPSHOT_VERSION

    price: Optional[float] = None
    market_cap: Optional[float] = None
    adv_usd: Optional[float] = None
    spread_bps: Optional[float] = None
    volume: Optional[float] = None
    shares_outstanding: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary representation."""
        return {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "source_id": self.source_id,
            "input_hash": self.input_hash,
            "schema_version": self.schema_version,
            "price": float(self.price) if self.price is not None else None,
            "market_cap": float(self.market_cap) if self.market_cap is not None else None,
            "adv_usd": float(self.adv_usd) if self.adv_usd is not None else None,
            "spread_bps": float(self.spread_bps) if self.spread_bps is not None else None,
            "volume": float(self.volume) if self.volume is not None else None,
            "shares_outstanding": float(self.shares_outstanding) if self.shares_outstanding is not None else None,
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketSnapshot":
        """Create from dictionary."""
        return cls(
            ticker=str(d["ticker"]).upper(),
            as_of_date=str(d["as_of_date"]),
            source_id=str(d["source_id"]),
            input_hash=str(d["input_hash"]),
            schema_version=str(d.get("schema_version", MARKET_SNAPSHOT_VERSION)),
            price=d.get("price"),
            market_cap=d.get("market_cap"),
            adv_usd=d.get("adv_usd"),
            spread_bps=d.get("spread_bps"),
            volume=d.get("volume"),
            shares_outstanding=d.get("shares_outstanding"),
        )


@dataclass(frozen=True)
class FinancialSnapshot:
    """Point-in-time financial health snapshot for a ticker.

    Fields:
    - ticker: Stock ticker symbol (uppercase)
    - as_of_date: ISO date string
    - source_id: Data source identifier
    - input_hash: SHA256 of raw input
    - schema_version: Schema version string

    Financial data:
    - runway_months: Cash runway in months
    - cash_position: Cash and equivalents (USD)
    - burn_rate: Monthly burn rate (USD)
    - debt_to_equity: Debt to equity ratio
    - current_ratio: Current assets / current liabilities
    """
    ticker: str
    as_of_date: str
    source_id: str
    input_hash: str
    schema_version: str = FINANCIAL_SNAPSHOT_VERSION

    runway_months: Optional[float] = None
    cash_position: Optional[float] = None
    burn_rate: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary representation."""
        return {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "source_id": self.source_id,
            "input_hash": self.input_hash,
            "schema_version": self.schema_version,
            "runway_months": float(self.runway_months) if self.runway_months is not None else None,
            "cash_position": float(self.cash_position) if self.cash_position is not None else None,
            "burn_rate": float(self.burn_rate) if self.burn_rate is not None else None,
            "debt_to_equity": float(self.debt_to_equity) if self.debt_to_equity is not None else None,
            "current_ratio": float(self.current_ratio) if self.current_ratio is not None else None,
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FinancialSnapshot":
        """Create from dictionary."""
        return cls(
            ticker=str(d["ticker"]).upper(),
            as_of_date=str(d["as_of_date"]),
            source_id=str(d["source_id"]),
            input_hash=str(d["input_hash"]),
            schema_version=str(d.get("schema_version", FINANCIAL_SNAPSHOT_VERSION)),
            runway_months=d.get("runway_months"),
            cash_position=d.get("cash_position"),
            burn_rate=d.get("burn_rate"),
            debt_to_equity=d.get("debt_to_equity"),
            current_ratio=d.get("current_ratio"),
        )


@dataclass(frozen=True)
class ManagerPosition:
    """Single manager's position in a ticker."""
    manager_cik: str
    manager_name: str
    shares: int
    value_usd: float
    change_shares: Optional[int] = None
    change_pct: Optional[float] = None
    filing_date: Optional[str] = None
    is_new_position: bool = False
    is_closed_position: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary."""
        return {
            "manager_cik": self.manager_cik,
            "manager_name": self.manager_name,
            "shares": int(self.shares),
            "value_usd": float(self.value_usd),
            "change_shares": int(self.change_shares) if self.change_shares is not None else None,
            "change_pct": float(self.change_pct) if self.change_pct is not None else None,
            "filing_date": self.filing_date,
            "is_new_position": self.is_new_position,
            "is_closed_position": self.is_closed_position,
        }


@dataclass(frozen=True)
class InstitutionalSnapshot:
    """Point-in-time institutional ownership snapshot for a ticker.

    Captures institutional manager positions and aggregate flows.
    """
    ticker: str
    as_of_date: str
    source_id: str
    input_hash: str
    schema_version: str = INSTITUTIONAL_SNAPSHOT_VERSION

    # Aggregate metrics
    total_institutional_shares: Optional[int] = None
    total_institutional_value: Optional[float] = None
    manager_count: int = 0
    net_buyers: int = 0
    net_sellers: int = 0
    new_positions: int = 0
    closed_positions: int = 0
    net_flow_kusd: Optional[float] = None  # Net flow in thousands USD

    # Individual positions (sorted by manager_cik)
    positions: tuple = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary representation."""
        # Sort positions by manager_cik for determinism
        sorted_positions = sorted(
            [p.to_dict() if hasattr(p, 'to_dict') else p for p in self.positions],
            key=lambda x: x.get("manager_cik", "")
        )
        return {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "source_id": self.source_id,
            "input_hash": self.input_hash,
            "schema_version": self.schema_version,
            "total_institutional_shares": int(self.total_institutional_shares) if self.total_institutional_shares is not None else None,
            "total_institutional_value": float(self.total_institutional_value) if self.total_institutional_value is not None else None,
            "manager_count": int(self.manager_count),
            "net_buyers": int(self.net_buyers),
            "net_sellers": int(self.net_sellers),
            "new_positions": int(self.new_positions),
            "closed_positions": int(self.closed_positions),
            "net_flow_kusd": float(self.net_flow_kusd) if self.net_flow_kusd is not None else None,
            "positions": sorted_positions,
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InstitutionalSnapshot":
        """Create from dictionary."""
        positions = tuple(
            ManagerPosition(**p) if isinstance(p, dict) else p
            for p in d.get("positions", [])
        )
        return cls(
            ticker=str(d["ticker"]).upper(),
            as_of_date=str(d["as_of_date"]),
            source_id=str(d["source_id"]),
            input_hash=str(d["input_hash"]),
            schema_version=str(d.get("schema_version", INSTITUTIONAL_SNAPSHOT_VERSION)),
            total_institutional_shares=d.get("total_institutional_shares"),
            total_institutional_value=d.get("total_institutional_value"),
            manager_count=d.get("manager_count", 0),
            net_buyers=d.get("net_buyers", 0),
            net_sellers=d.get("net_sellers", 0),
            new_positions=d.get("new_positions", 0),
            closed_positions=d.get("closed_positions", 0),
            net_flow_kusd=d.get("net_flow_kusd"),
            positions=positions,
        )


@dataclass(frozen=True)
class CatalystSnapshot:
    """Point-in-time catalyst/event snapshot for a ticker.

    Captures upcoming catalysts like FDA dates, earnings, trial readouts.
    """
    ticker: str
    as_of_date: str
    source_id: str
    input_hash: str
    schema_version: str = CATALYST_SNAPSHOT_VERSION

    # Catalyst data
    next_catalyst_date: Optional[str] = None
    next_catalyst_type: Optional[str] = None  # PDUFA, ADCOMM, EARNINGS, TRIAL_READOUT
    next_catalyst_description: Optional[str] = None
    days_to_catalyst: Optional[int] = None
    catalyst_count_90d: int = 0  # Catalysts within 90 days

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary representation."""
        return {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "source_id": self.source_id,
            "input_hash": self.input_hash,
            "schema_version": self.schema_version,
            "next_catalyst_date": self.next_catalyst_date,
            "next_catalyst_type": self.next_catalyst_type,
            "next_catalyst_description": self.next_catalyst_description,
            "days_to_catalyst": int(self.days_to_catalyst) if self.days_to_catalyst is not None else None,
            "catalyst_count_90d": int(self.catalyst_count_90d),
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CatalystSnapshot":
        """Create from dictionary."""
        return cls(
            ticker=str(d["ticker"]).upper(),
            as_of_date=str(d["as_of_date"]),
            source_id=str(d["source_id"]),
            input_hash=str(d["input_hash"]),
            schema_version=str(d.get("schema_version", CATALYST_SNAPSHOT_VERSION)),
            next_catalyst_date=d.get("next_catalyst_date"),
            next_catalyst_type=d.get("next_catalyst_type"),
            next_catalyst_description=d.get("next_catalyst_description"),
            days_to_catalyst=d.get("days_to_catalyst"),
            catalyst_count_90d=d.get("catalyst_count_90d", 0),
        )


@dataclass(frozen=True)
class UniverseSnapshot:
    """Point-in-time universe definition snapshot.

    Lists all tickers in the analysis universe with basic metadata.
    """
    as_of_date: str
    source_id: str
    input_hash: str
    schema_version: str = UNIVERSE_SNAPSHOT_VERSION

    # Universe data (sorted by ticker)
    tickers: tuple = field(default_factory=tuple)
    ticker_metadata: tuple = field(default_factory=tuple)  # List of dicts with ticker info

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary representation."""
        # Sort tickers for determinism
        sorted_tickers = tuple(sorted(self.tickers))
        sorted_metadata = tuple(sorted(
            [m if isinstance(m, dict) else {} for m in self.ticker_metadata],
            key=lambda x: x.get("ticker", "")
        ))
        return {
            "as_of_date": self.as_of_date,
            "source_id": self.source_id,
            "input_hash": self.input_hash,
            "schema_version": self.schema_version,
            "tickers": list(sorted_tickers),
            "ticker_metadata": list(sorted_metadata),
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UniverseSnapshot":
        """Create from dictionary."""
        return cls(
            as_of_date=str(d["as_of_date"]),
            source_id=str(d["source_id"]),
            input_hash=str(d["input_hash"]),
            schema_version=str(d.get("schema_version", UNIVERSE_SNAPSHOT_VERSION)),
            tickers=tuple(sorted(d.get("tickers", []))),
            ticker_metadata=tuple(d.get("ticker_metadata", [])),
        )


@dataclass
class SnapshotBundle:
    """Collection of all snapshots for a single ticker.

    Used as input to feature computation.
    """
    ticker: str
    as_of_date: str

    market: Optional[MarketSnapshot] = None
    financial: Optional[FinancialSnapshot] = None
    institutional: Optional[InstitutionalSnapshot] = None
    catalyst: Optional[CatalystSnapshot] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary representation."""
        return {
            "ticker": self.ticker.upper(),
            "as_of_date": self.as_of_date,
            "market": self.market.to_dict() if self.market else None,
            "financial": self.financial.to_dict() if self.financial else None,
            "institutional": self.institutional.to_dict() if self.institutional else None,
            "catalyst": self.catalyst.to_dict() if self.catalyst else None,
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    def compute_bundle_hash(self) -> str:
        """Compute deterministic hash of the entire bundle."""
        return compute_hash_from_dict(self.to_dict())
