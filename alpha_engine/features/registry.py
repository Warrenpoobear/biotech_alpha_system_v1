"""Feature Registry and Feature Store.

Provides a modular feature framework with:
- FeatureSpec: Defines feature computation
- FeatureBundle: Collection of computed features with provenance
- Deterministic caching keyed by (ticker, as_of_date, feature_version, input_hashes)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from pathlib import Path

from alpha_engine.contracts import (
    SnapshotBundle,
    FeatureVector,
    canonical_json_dumps,
    canonical_json_loads,
    compute_hash_from_dict,
)


class MissingPolicy(str, Enum):
    """Policy for handling missing input data."""
    FAIL_CLOSED = "FAIL_CLOSED"  # Raise error if inputs missing
    UNKNOWN_OK = "UNKNOWN_OK"    # Return None for feature, continue
    DEFAULT_OK = "DEFAULT_OK"    # Use default value, continue


class FeatureComputeError(Exception):
    """Raised when feature computation fails."""
    pass


@dataclass(frozen=True)
class FeatureSpec:
    """Specification for a feature computation.

    Attributes:
        name: Unique feature name
        version: Feature version string
        required_inputs: List of required snapshot types ("market", "financial", etc.)
        compute_fn: Function (SnapshotBundle) -> Optional[float]
        missing_policy: How to handle missing inputs
        default_value: Default value if missing_policy is DEFAULT_OK
        description: Human-readable description
    """
    name: str
    version: str
    required_inputs: tuple
    compute_fn: Callable[[SnapshotBundle], Optional[float]]
    missing_policy: MissingPolicy = MissingPolicy.UNKNOWN_OK
    default_value: Optional[float] = None
    description: str = ""

    def compute(self, bundle: SnapshotBundle) -> Optional[float]:
        """Compute feature value from snapshot bundle.

        Returns:
            Feature value or None if computation failed/skipped
        """
        # Check required inputs
        for input_type in self.required_inputs:
            snapshot = getattr(bundle, input_type, None)
            if snapshot is None:
                if self.missing_policy == MissingPolicy.FAIL_CLOSED:
                    raise FeatureComputeError(
                        f"Missing required input '{input_type}' for feature '{self.name}'"
                    )
                elif self.missing_policy == MissingPolicy.DEFAULT_OK:
                    return self.default_value
                else:  # UNKNOWN_OK
                    return None

        try:
            return self.compute_fn(bundle)
        except Exception as e:
            if self.missing_policy == MissingPolicy.FAIL_CLOSED:
                raise FeatureComputeError(f"Feature '{self.name}' computation failed: {e}")
            elif self.missing_policy == MissingPolicy.DEFAULT_OK:
                return self.default_value
            return None

    def get_input_hashes(self, bundle: SnapshotBundle) -> List[str]:
        """Get input hashes used for this feature computation."""
        hashes = []
        for input_type in self.required_inputs:
            snapshot = getattr(bundle, input_type, None)
            if snapshot and hasattr(snapshot, 'input_hash'):
                hashes.append(snapshot.input_hash)
        return sorted(hashes)


class FeatureRegistry:
    """Registry of available features.

    Manages feature specifications and provides feature computation.
    """

    def __init__(self):
        self._features: Dict[str, FeatureSpec] = {}

    def register(self, spec: FeatureSpec) -> None:
        """Register a feature specification."""
        key = f"{spec.name}:{spec.version}"
        self._features[key] = spec

    def get(self, name: str, version: Optional[str] = None) -> Optional[FeatureSpec]:
        """Get a feature specification.

        If version is None, returns the latest version.
        """
        if version:
            key = f"{name}:{version}"
            return self._features.get(key)

        # Find latest version
        matching = [k for k in self._features if k.startswith(f"{name}:")]
        if not matching:
            return None
        latest = sorted(matching)[-1]
        return self._features[latest]

    def list_features(self) -> List[str]:
        """List all registered feature names."""
        return sorted(set(k.split(":")[0] for k in self._features))

    def compute_features(
        self,
        bundle: SnapshotBundle,
        feature_names: Optional[List[str]] = None,
        score_version: str = "v1",
        parameters_hash: str = "",
        run_id: str = "",
    ) -> FeatureVector:
        """Compute all specified features for a bundle.

        Args:
            bundle: Input snapshot bundle
            feature_names: List of features to compute (None = all)
            score_version: Version string for output
            parameters_hash: Hash of parameters used
            run_id: Run identifier

        Returns:
            FeatureVector with computed features and provenance
        """
        if feature_names is None:
            feature_names = self.list_features()

        features: Dict[str, Optional[float]] = {}
        provenance: Dict[str, List[str]] = {}
        missing_features: Dict[str, str] = {}

        for name in sorted(feature_names):
            spec = self.get(name)
            if spec is None:
                missing_features[name] = "Feature not registered"
                continue

            try:
                value = spec.compute(bundle)
                features[name] = value
                provenance[name] = spec.get_input_hashes(bundle)
                if value is None:
                    missing_features[name] = "Computation returned None"
            except FeatureComputeError as e:
                features[name] = None
                missing_features[name] = str(e)

        return FeatureVector(
            ticker=bundle.ticker,
            as_of_date=bundle.as_of_date,
            score_version=score_version,
            parameters_hash=parameters_hash,
            run_id=run_id,
            features=features,
            provenance=provenance,
            missing_features=missing_features,
        )


# ============================================================
# Built-in Feature Definitions
# ============================================================

def _compute_institutional_mgr_count(bundle: SnapshotBundle) -> Optional[float]:
    """Number of institutional managers holding the stock."""
    if bundle.institutional is None:
        return None
    return float(bundle.institutional.manager_count)


def _compute_institutional_net_buyers(bundle: SnapshotBundle) -> Optional[float]:
    """Number of managers increasing positions."""
    if bundle.institutional is None:
        return None
    return float(bundle.institutional.net_buyers)


def _compute_institutional_net_sellers(bundle: SnapshotBundle) -> Optional[float]:
    """Number of managers decreasing positions."""
    if bundle.institutional is None:
        return None
    return float(bundle.institutional.net_sellers)


def _compute_institutional_net_flow(bundle: SnapshotBundle) -> Optional[float]:
    """Net institutional flow in thousands USD."""
    if bundle.institutional is None:
        return None
    return bundle.institutional.net_flow_kusd


def _compute_institutional_buyer_ratio(bundle: SnapshotBundle) -> Optional[float]:
    """Ratio of buyers to total active managers."""
    if bundle.institutional is None:
        return None
    total = bundle.institutional.net_buyers + bundle.institutional.net_sellers
    if total == 0:
        return 0.5  # Neutral if no activity
    return bundle.institutional.net_buyers / total


def _compute_institutional_new_positions(bundle: SnapshotBundle) -> Optional[float]:
    """Number of new institutional positions."""
    if bundle.institutional is None:
        return None
    return float(bundle.institutional.new_positions)


def _compute_market_price(bundle: SnapshotBundle) -> Optional[float]:
    """Current stock price."""
    if bundle.market is None:
        return None
    return bundle.market.price


def _compute_market_cap(bundle: SnapshotBundle) -> Optional[float]:
    """Market capitalization."""
    if bundle.market is None:
        return None
    return bundle.market.market_cap


def _compute_adv_usd(bundle: SnapshotBundle) -> Optional[float]:
    """Average daily volume in USD."""
    if bundle.market is None:
        return None
    return bundle.market.adv_usd


def _compute_runway_months(bundle: SnapshotBundle) -> Optional[float]:
    """Cash runway in months."""
    if bundle.financial is None:
        return None
    return bundle.financial.runway_months


def _compute_cash_position(bundle: SnapshotBundle) -> Optional[float]:
    """Cash position in USD."""
    if bundle.financial is None:
        return None
    return bundle.financial.cash_position


def _compute_catalyst_days(bundle: SnapshotBundle) -> Optional[float]:
    """Days until next catalyst."""
    if bundle.catalyst is None:
        return None
    return float(bundle.catalyst.days_to_catalyst) if bundle.catalyst.days_to_catalyst else None


def _compute_conviction_proxy(bundle: SnapshotBundle) -> Optional[float]:
    """Proxy for institutional conviction.

    Computed as: (new_positions + net_buyers) / manager_count
    Higher values indicate stronger conviction.
    """
    if bundle.institutional is None:
        return None
    mgr_count = bundle.institutional.manager_count
    if mgr_count == 0:
        return None
    new_pos = bundle.institutional.new_positions
    net_buy = bundle.institutional.net_buyers
    return (new_pos + net_buy) / mgr_count


def _compute_concentration_hhi(bundle: SnapshotBundle) -> Optional[float]:
    """Herfindahl-Hirschman Index for institutional concentration.

    Lower is more diversified, higher is more concentrated.
    Range: 0 to 10000 (monopoly)
    """
    if bundle.institutional is None or not bundle.institutional.positions:
        return None

    total_value = bundle.institutional.total_institutional_value
    if not total_value or total_value == 0:
        return None

    hhi = 0.0
    for pos in bundle.institutional.positions:
        share = (pos.value_usd / total_value) * 100
        hhi += share ** 2

    return hhi


# Create default registry with built-in features
def create_default_registry() -> FeatureRegistry:
    """Create a registry with all built-in features."""
    registry = FeatureRegistry()

    # Institutional features
    registry.register(FeatureSpec(
        name="institutional_mgr_count",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_institutional_mgr_count,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Number of institutional managers holding the stock",
    ))

    registry.register(FeatureSpec(
        name="institutional_net_buyers",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_institutional_net_buyers,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Number of managers increasing positions",
    ))

    registry.register(FeatureSpec(
        name="institutional_net_sellers",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_institutional_net_sellers,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Number of managers decreasing positions",
    ))

    registry.register(FeatureSpec(
        name="institutional_net_flow_kusd",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_institutional_net_flow,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Net institutional flow in thousands USD",
    ))

    registry.register(FeatureSpec(
        name="institutional_buyer_ratio",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_institutional_buyer_ratio,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Ratio of buyers to total active managers",
    ))

    registry.register(FeatureSpec(
        name="institutional_new_positions",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_institutional_new_positions,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Number of new institutional positions",
    ))

    registry.register(FeatureSpec(
        name="conviction_proxy",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_conviction_proxy,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Proxy for institutional conviction",
    ))

    registry.register(FeatureSpec(
        name="concentration_hhi",
        version="1.0",
        required_inputs=("institutional",),
        compute_fn=_compute_concentration_hhi,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Herfindahl-Hirschman Index for institutional concentration",
    ))

    # Market features
    registry.register(FeatureSpec(
        name="price",
        version="1.0",
        required_inputs=("market",),
        compute_fn=_compute_market_price,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Current stock price",
    ))

    registry.register(FeatureSpec(
        name="market_cap",
        version="1.0",
        required_inputs=("market",),
        compute_fn=_compute_market_cap,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Market capitalization",
    ))

    registry.register(FeatureSpec(
        name="adv_usd",
        version="1.0",
        required_inputs=("market",),
        compute_fn=_compute_adv_usd,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Average daily volume in USD",
    ))

    # Financial features
    registry.register(FeatureSpec(
        name="runway_months",
        version="1.0",
        required_inputs=("financial",),
        compute_fn=_compute_runway_months,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Cash runway in months",
    ))

    registry.register(FeatureSpec(
        name="cash_position",
        version="1.0",
        required_inputs=("financial",),
        compute_fn=_compute_cash_position,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Cash position in USD",
    ))

    # Catalyst features
    registry.register(FeatureSpec(
        name="days_to_catalyst",
        version="1.0",
        required_inputs=("catalyst",),
        compute_fn=_compute_catalyst_days,
        missing_policy=MissingPolicy.UNKNOWN_OK,
        description="Days until next catalyst",
    ))

    return registry


class FeatureStore:
    """Persistent storage for computed features.

    Writes features to JSONL files with stable ordering.
    """

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(
        self,
        ticker: str,
        as_of_date: str,
        feature_version: str,
        input_hashes: Dict[str, str],
    ) -> str:
        """Generate deterministic cache key."""
        key_data = {
            "ticker": ticker.upper(),
            "as_of_date": as_of_date,
            "feature_version": feature_version,
            "input_hashes": dict(sorted(input_hashes.items())),
        }
        return compute_hash_from_dict(key_data)[:16]

    def write_feature_vector(self, fv: FeatureVector) -> Path:
        """Write a feature vector to storage.

        Returns path to written file.
        """
        # Create date directory
        date_dir = self.base_path / f"as_of={fv.as_of_date}"
        date_dir.mkdir(exist_ok=True)

        # Write to JSONL file
        output_file = date_dir / f"{fv.ticker.upper()}_features.json"
        with open(output_file, 'w') as f:
            f.write(fv.to_json())

        return output_file

    def write_batch(self, feature_vectors: List[FeatureVector], as_of_date: str) -> Path:
        """Write batch of feature vectors to single JSONL file.

        Returns path to written file.
        """
        date_dir = self.base_path / f"as_of={as_of_date}"
        date_dir.mkdir(exist_ok=True)

        output_file = date_dir / "features.jsonl"

        # Sort by ticker for determinism
        sorted_fvs = sorted(feature_vectors, key=lambda x: x.ticker.upper())

        with open(output_file, 'w') as f:
            for fv in sorted_fvs:
                f.write(fv.to_json() + "\n")

        return output_file

    def read_batch(self, as_of_date: str) -> List[FeatureVector]:
        """Read batch of feature vectors from JSONL file."""
        date_dir = self.base_path / f"as_of={as_of_date}"
        input_file = date_dir / "features.jsonl"

        if not input_file.exists():
            return []

        vectors = []
        with open(input_file, 'r') as f:
            for line in f:
                if line.strip():
                    d = canonical_json_loads(line)
                    vectors.append(FeatureVector(
                        ticker=d["ticker"],
                        as_of_date=d["as_of_date"],
                        score_version=d["score_version"],
                        parameters_hash=d["parameters_hash"],
                        run_id=d["run_id"],
                        features=d.get("features", {}),
                        provenance=d.get("provenance", {}),
                        missing_features=d.get("missing_features", {}),
                    ))

        return vectors
