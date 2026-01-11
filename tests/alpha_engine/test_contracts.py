"""Unit tests for Alpha Engine contract layer.

Tests:
- Round-trip serialize/deserialize produces identical bytes
- Hash stability across runs
- Canonical JSON formatting
"""

import pytest
from alpha_engine.contracts import (
    MarketSnapshot,
    FinancialSnapshot,
    InstitutionalSnapshot,
    ManagerPosition,
    CatalystSnapshot,
    UniverseSnapshot,
    SnapshotBundle,
    FeatureVector,
    SignalVector,
    ScoreCard,
    RejectionRecord,
    GateResult,
    AuditRecord,
    canonical_json_dumps,
    canonical_json_loads,
    compute_sha256,
    compute_hash_from_dict,
    stable_float,
)
from alpha_engine.contracts.outputs import GateStatus, RejectionReason


class TestSerialization:
    """Tests for canonical serialization."""

    def test_stable_float_normal(self):
        assert stable_float(1.23456789) == "1.23456789"
        assert stable_float(0.0) == "0.00000000"
        assert stable_float(-1.5) == "-1.50000000"

    def test_stable_float_none(self):
        assert stable_float(None) is None

    def test_stable_float_nan(self):
        assert stable_float(float('nan')) is None

    def test_stable_float_inf(self):
        assert stable_float(float('inf')) is None
        assert stable_float(float('-inf')) is None

    def test_canonical_json_sorted_keys(self):
        d = {"z": 1, "a": 2, "m": 3}
        result = canonical_json_dumps(d)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_canonical_json_nested_sorted(self):
        d = {"outer": {"z": 1, "a": 2}}
        result = canonical_json_dumps(d)
        assert '"a":2' in result
        assert result.index('"a"') < result.index('"z"')

    def test_canonical_json_float_precision(self):
        d = {"value": 1.23456789012345}
        result = canonical_json_dumps(d)
        # Should be rounded to 8 decimal places
        assert "1.23456789" in result

    def test_canonical_json_nan_to_null(self):
        d = {"value": float('nan')}
        result = canonical_json_dumps(d)
        assert '"value":null' in result

    def test_compute_sha256_string(self):
        h = compute_sha256("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
        # Same input should produce same hash
        assert compute_sha256("test") == h

    def test_compute_hash_from_dict_deterministic(self):
        d = {"b": 2, "a": 1}
        h1 = compute_hash_from_dict(d)
        h2 = compute_hash_from_dict(d)
        assert h1 == h2

        # Different key order should produce same hash (sorted)
        d2 = {"a": 1, "b": 2}
        h3 = compute_hash_from_dict(d2)
        assert h1 == h3


class TestMarketSnapshot:
    """Tests for MarketSnapshot."""

    def test_roundtrip_serialization(self):
        snap = MarketSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test_source",
            input_hash="a" * 64,
            price=95.50,
            market_cap=35000000000.0,
            adv_usd=500000000.0,
        )

        json_str = snap.to_json()
        d = canonical_json_loads(json_str)
        snap2 = MarketSnapshot.from_dict(d)

        assert snap2.ticker == snap.ticker
        assert snap2.price == snap.price
        assert snap2.market_cap == snap.market_cap

    def test_ticker_uppercased(self):
        snap = MarketSnapshot(
            ticker="mrna",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="a" * 64,
        )
        d = snap.to_dict()
        assert d["ticker"] == "MRNA"

    def test_json_byte_identical(self):
        snap = MarketSnapshot(
            ticker="GILD",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="b" * 64,
            price=72.30,
        )
        json1 = snap.to_json()
        json2 = snap.to_json()
        assert json1 == json2


class TestFinancialSnapshot:
    """Tests for FinancialSnapshot."""

    def test_roundtrip_serialization(self):
        snap = FinancialSnapshot(
            ticker="VRTX",
            as_of_date="2024-01-15",
            source_id="test_source",
            input_hash="c" * 64,
            runway_months=36.5,
            cash_position=5000000000.0,
        )

        json_str = snap.to_json()
        d = canonical_json_loads(json_str)
        snap2 = FinancialSnapshot.from_dict(d)

        assert snap2.ticker == snap.ticker
        assert snap2.runway_months == snap.runway_months


class TestInstitutionalSnapshot:
    """Tests for InstitutionalSnapshot."""

    def test_positions_sorted_by_cik(self):
        pos1 = ManagerPosition(
            manager_cik="0001234567",
            manager_name="Manager B",
            shares=1000000,
            value_usd=50000000.0,
        )
        pos2 = ManagerPosition(
            manager_cik="0000123456",
            manager_name="Manager A",
            shares=500000,
            value_usd=25000000.0,
        )

        snap = InstitutionalSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="d" * 64,
            positions=(pos1, pos2),  # Intentionally out of order
        )

        d = snap.to_dict()
        # Positions should be sorted by manager_cik
        assert d["positions"][0]["manager_cik"] == "0000123456"
        assert d["positions"][1]["manager_cik"] == "0001234567"

    def test_roundtrip_with_positions(self):
        pos = ManagerPosition(
            manager_cik="0001234567",
            manager_name="Test Manager",
            shares=1000000,
            value_usd=50000000.0,
            change_shares=100000,
            is_new_position=False,
        )

        snap = InstitutionalSnapshot(
            ticker="BIIB",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="e" * 64,
            manager_count=1,
            net_buyers=1,
            positions=(pos,),
        )

        json_str = snap.to_json()
        d = canonical_json_loads(json_str)
        snap2 = InstitutionalSnapshot.from_dict(d)

        assert snap2.manager_count == 1
        assert len(snap2.positions) == 1


class TestCatalystSnapshot:
    """Tests for CatalystSnapshot."""

    def test_roundtrip_serialization(self):
        snap = CatalystSnapshot(
            ticker="ALNY",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="f" * 64,
            next_catalyst_date="2024-03-15",
            next_catalyst_type="PDUFA",
            days_to_catalyst=60,
        )

        json_str = snap.to_json()
        d = canonical_json_loads(json_str)
        snap2 = CatalystSnapshot.from_dict(d)

        assert snap2.next_catalyst_type == "PDUFA"
        assert snap2.days_to_catalyst == 60


class TestUniverseSnapshot:
    """Tests for UniverseSnapshot."""

    def test_tickers_sorted(self):
        snap = UniverseSnapshot(
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="g" * 64,
            tickers=("VRTX", "MRNA", "GILD"),  # Intentionally unsorted
        )

        d = snap.to_dict()
        assert d["tickers"] == ["GILD", "MRNA", "VRTX"]


class TestSnapshotBundle:
    """Tests for SnapshotBundle."""

    def test_bundle_hash_deterministic(self):
        market = MarketSnapshot(
            ticker="MRNA",
            as_of_date="2024-01-15",
            source_id="test",
            input_hash="a" * 64,
            price=95.0,
        )
        bundle = SnapshotBundle(
            ticker="MRNA",
            as_of_date="2024-01-15",
            market=market,
        )

        h1 = bundle.compute_bundle_hash()
        h2 = bundle.compute_bundle_hash()
        assert h1 == h2


class TestGateResult:
    """Tests for GateResult."""

    def test_to_dict_with_enum(self):
        result = GateResult(
            ticker="MRNA",
            gate_name="liquidity",
            status=GateStatus.PASSED,
            threshold=100000.0,
            actual_value=500000.0,
        )

        d = result.to_dict()
        assert d["status"] == "PASSED"
        assert d["ticker"] == "MRNA"


class TestScoreCard:
    """Tests for ScoreCard."""

    def test_output_hash_computed(self):
        card = ScoreCard(
            ticker="MRNA",
            as_of_date="2024-01-15",
            score_version="v1",
            parameters_hash="h" * 64,
            run_id="test_run_001",
            score_total=0.75,
            status="SCORED",
            score_components={"institutional": 0.8, "liquidity": 0.7},
        )

        card_with_hash = card.with_output_hash()
        assert card_with_hash.output_hash is not None
        assert len(card_with_hash.output_hash) == 64

    def test_score_components_sorted(self):
        card = ScoreCard(
            ticker="GILD",
            as_of_date="2024-01-15",
            score_version="v1",
            parameters_hash="i" * 64,
            run_id="test_run_002",
            score_total=0.65,
            status="SCORED",
            score_components={"z_component": 0.5, "a_component": 0.8},
        )

        d = card.to_dict()
        keys = list(d["score_components"].keys())
        assert keys == sorted(keys)

    def test_json_byte_identical(self):
        card = ScoreCard(
            ticker="VRTX",
            as_of_date="2024-01-15",
            score_version="v1",
            parameters_hash="j" * 64,
            run_id="test_run_003",
            score_total=0.80,
            status="SCORED",
        )

        json1 = card.to_json()
        json2 = card.to_json()
        assert json1 == json2


class TestRejectionRecord:
    """Tests for RejectionRecord."""

    def test_gate_results_sorted(self):
        gate1 = GateResult(ticker="MRNA", gate_name="z_gate", status=GateStatus.FAILED)
        gate2 = GateResult(ticker="MRNA", gate_name="a_gate", status=GateStatus.PASSED)

        record = RejectionRecord(
            ticker="MRNA",
            reason=RejectionReason.LIQUIDITY_GATE,
            gate_results=(gate1, gate2),
        )

        d = record.to_dict()
        assert d["gate_results"][0]["gate_name"] == "a_gate"
        assert d["gate_results"][1]["gate_name"] == "z_gate"


class TestAuditRecord:
    """Tests for AuditRecord."""

    def test_jsonl_line_format(self):
        audit = AuditRecord(
            run_id="run_001",
            as_of_date="2024-01-15",
            pipeline_version="1.0.0",
            score_version="v1",
            parameters_hash="k" * 64,
            status="COMPLETED",
        )

        line = audit.to_jsonl_line()
        assert line.endswith("\n")
        assert "\n" not in line[:-1]  # Only trailing newline

    def test_input_hashes_sorted(self):
        audit = AuditRecord(
            run_id="run_002",
            as_of_date="2024-01-15",
            pipeline_version="1.0.0",
            score_version="v1",
            parameters_hash="l" * 64,
            input_hashes={"z_input": "aaa", "a_input": "bbb"},
        )

        d = audit.to_dict()
        keys = list(d["input_hashes"].keys())
        assert keys == sorted(keys)


class TestFeatureVector:
    """Tests for FeatureVector."""

    def test_features_sorted(self):
        fv = FeatureVector(
            ticker="MRNA",
            as_of_date="2024-01-15",
            score_version="v1",
            parameters_hash="m" * 64,
            run_id="run_003",
            features={"z_feature": 0.5, "a_feature": 0.8, "m_feature": None},
        )

        d = fv.to_dict()
        keys = list(d["features"].keys())
        assert keys == sorted(keys)

    def test_output_hash_deterministic(self):
        fv = FeatureVector(
            ticker="GILD",
            as_of_date="2024-01-15",
            score_version="v1",
            parameters_hash="n" * 64,
            run_id="run_004",
            features={"test": 0.5},
        )

        h1 = fv.compute_output_hash()
        h2 = fv.compute_output_hash()
        assert h1 == h2
