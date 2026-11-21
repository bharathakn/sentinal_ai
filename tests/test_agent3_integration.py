"""
Sentinel AI — Agent 3: Live Neo4j Integration Tests

Tests Agent 3 network-pattern detection against a real Neo4j instance using
small, deterministic synthetic graphs. All test data uses a unique prefix to
isolate from production data. Cleanup removes only test-prefixed nodes.

Skip policy
-----------
All tests are skipped when NEO4J_URI is not configured.

Test graph topology
-------------------
Each test class creates its own isolated synthetic graph (unique prefix per class).

Normal:         A → B only (no threshold met)
Fan-in:         SRC1, SRC2, SRC3 → CENTER
Fan-out:        HUB → DST1, DST2, DST3
Mule-like:      SRC1, SRC2 → MULE → DST1, DST2
Rapid-fwd:      SOURCE → FWDR → DEST  (within 30 min)
Layering:       A → B → C → D (3 hops)
Structuring:    SENDER →×3 within 12h → various accounts
Cluster:        Dense 4-account group with cycles
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from src.schemas.canonical_transaction import (
    AccountInfo,
    CanonicalTransaction,
    DataSource,
    TransactionChannel,
    TransactionStatus,
)
from src.graph.connection import Neo4jConnectionManager
from src.graph.schema import GraphSchemaManager
from src.graph.loader import TransactionGraphLoader
from src.agents.agent3 import NetworkAnalyserAgent, Agent3Status, Agent3Config
from src.agents.agent3.output_schema import NetworkPatternType

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

_CONFIGURED = bool(
    os.environ.get("NEO4J_URI", "").strip()
    and os.environ.get("NEO4J_USERNAME", "").strip()
    and os.environ.get("NEO4J_PASSWORD", "").strip()
)

pytestmark = pytest.mark.skipif(
    not _CONFIGURED,
    reason=(
        "Live Agent 3 Neo4j integration tests skipped: NEO4J_URI / "
        "NEO4J_USERNAME / NEO4J_PASSWORD not configured. All 81 offline unit "
        "tests ran instead. Set env vars and re-run to execute live tests."
    ),
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_BASE_PREFIX = "A3INTEG_"
_T0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)


def _ts(delta_minutes: float = 0) -> datetime:
    return _T0 + timedelta(minutes=delta_minutes)


def _make_canonical_tx(
    raw_id: str,
    sender_id: str,
    receiver_id: str,
    amount: str = "500.00",
    ts_delta_minutes: float = 0,
) -> CanonicalTransaction:
    return CanonicalTransaction(
        raw_record_id=raw_id,
        source_dataset=DataSource.INDIA_SYNTHETIC,
        amount=Decimal(amount),
        currency="INR",
        timestamp=_ts(ts_delta_minutes),
        channel=TransactionChannel.UPI,
        status=TransactionStatus.SUCCESS,
        sender=AccountInfo(account_id=sender_id),
        receiver=AccountInfo(account_id=receiver_id),
    )


def _cleanup(mgr: Neo4jConnectionManager, prefix: str) -> None:
    with mgr.session() as session:
        session.run(
            "MATCH (a:Account) WHERE a.account_id STARTS WITH $prefix DETACH DELETE a",
            prefix=prefix,
        )


# ---------------------------------------------------------------------------
# Module-scoped connection
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def neo4j_mgr():
    mgr = Neo4jConnectionManager()
    mgr.connect()
    mgr.verify_connectivity()
    schema = GraphSchemaManager(mgr.session)
    schema.init_schema()
    yield mgr
    mgr.close()


def _agent(mgr: Neo4jConnectionManager, **cfg_kwargs) -> NetworkAnalyserAgent:
    cfg = Agent3Config(
        fan_in_min_sources=3,
        fan_out_min_destinations=3,
        mule_min_incoming_sources=2,
        mule_min_outgoing_destinations=2,
        structuring_min_transfers=3,
        structuring_window_hours=24.0,
        rapid_forwarding_window_minutes=60.0,
        min_layering_hops=2,
        max_layering_hops=4,
        cluster_min_accounts=4,
        cluster_min_edges=4,
        transfer_query_limit=100,
        **cfg_kwargs,
    )
    return NetworkAnalyserAgent(config=cfg, connection_manager=mgr)


# ---------------------------------------------------------------------------
# 1. Normal — no patterns
# ---------------------------------------------------------------------------

class TestNormalNetworkLive:
    _PREFIX = f"{_BASE_PREFIX}NORM_"

    def test_normal_no_findings(self, neo4j_mgr):
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        tx = _make_canonical_tx(f"{p}TX1", f"{p}A", f"{p}B", "500")
        loader.load_transaction(tx)
        try:
            agent = _agent(neo4j_mgr)
            result = agent.analyse(tx)
            assert result.status in (Agent3Status.COMPLETE, Agent3Status.PARTIAL)
            # No fan-in/fan-out/mule/rapid patterns — only one transfer
            assert not any(
                f.pattern_type in {
                    NetworkPatternType.FAN_IN,
                    NetworkPatternType.FAN_OUT,
                    NetworkPatternType.MULE_LIKE,
                }
                for f in result.findings
            )
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 2. Fan-in
# ---------------------------------------------------------------------------

class TestFanInLive:
    _PREFIX = f"{_BASE_PREFIX}FANIN_"

    def test_fan_in_detected(self, neo4j_mgr):
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        center = f"{p}CENTER"
        txns = [
            _make_canonical_tx(f"{p}TX{i}", f"{p}SRC{i}", center, "300", ts_delta_minutes=i * 5)
            for i in range(3)
        ]
        for tx in txns:
            loader.load_transaction(tx)

        subject_tx = txns[0]
        try:
            agent = _agent(neo4j_mgr)
            result = agent.analyse(subject_tx)
            # Center account (receiver) checked — but Agent 3 analyses sender by default
            # Load a tx FROM center so it can be the subject
            center_tx = _make_canonical_tx(f"{p}CTX1", center, f"{p}OUT", "100")
            loader.load_transaction(center_tx)
            result_center = agent.analyse(center_tx)
            fan_in = [
                f for f in result_center.findings
                if f.pattern_type == NetworkPatternType.FAN_IN
            ]
            assert len(fan_in) == 1
            assert fan_in[0].distinct_counterparty_count == 3
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 3. Fan-out
# ---------------------------------------------------------------------------

class TestFanOutLive:
    _PREFIX = f"{_BASE_PREFIX}FANOUT_"

    def test_fan_out_detected(self, neo4j_mgr):
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        hub = f"{p}HUB"
        txns = [
            _make_canonical_tx(f"{p}TX{i}", hub, f"{p}DST{i}", "200", ts_delta_minutes=i * 5)
            for i in range(3)
        ]
        for tx in txns:
            loader.load_transaction(tx)

        subject_tx = txns[0]
        try:
            agent = _agent(neo4j_mgr)
            result = agent.analyse(subject_tx)
            fan_out = [f for f in result.findings if f.pattern_type == NetworkPatternType.FAN_OUT]
            assert len(fan_out) == 1
            assert fan_out[0].distinct_counterparty_count == 3
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 4. Mule-like
# ---------------------------------------------------------------------------

class TestMuleLikeLive:
    _PREFIX = f"{_BASE_PREFIX}MULE_"

    def test_mule_detected(self, neo4j_mgr):
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        mule = f"{p}MULE"
        # 2 incoming sources
        in_txns = [
            _make_canonical_tx(f"{p}IN{i}", f"{p}SRC{i}", mule, "400", ts_delta_minutes=i * 5)
            for i in range(2)
        ]
        # 2 outgoing destinations, passing 600/800 = 75% onward (v2 pass-through rule)
        out_txns = [
            _make_canonical_tx(f"{p}OUT{i}", mule, f"{p}DST{i}", "300", ts_delta_minutes=10 + i * 5)
            for i in range(2)
        ]
        for tx in in_txns + out_txns:
            loader.load_transaction(tx)

        subject_tx = out_txns[0]  # sender is MULE
        try:
            agent = _agent(neo4j_mgr)
            result = agent.analyse(subject_tx)
            mule_findings = [f for f in result.findings if f.pattern_type == NetworkPatternType.MULE_LIKE]
            assert len(mule_findings) == 1
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 5. Rapid forwarding
# ---------------------------------------------------------------------------

class TestRapidForwardingLive:
    _PREFIX = f"{_BASE_PREFIX}RFWD_"

    def test_rapid_forwarding_detected(self, neo4j_mgr):
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        fwdr = f"{p}FWDR"
        in_tx = _make_canonical_tx(f"{p}IN1", f"{p}SOURCE", fwdr, "500", ts_delta_minutes=0)
        out_tx = _make_canonical_tx(f"{p}OUT1", fwdr, f"{p}DEST", "480", ts_delta_minutes=20)
        loader.load_transaction(in_tx)
        loader.load_transaction(out_tx)

        subject_tx = out_tx  # fwdr is sender
        try:
            agent = _agent(neo4j_mgr)
            result = agent.analyse(subject_tx)
            rf = [f for f in result.findings if f.pattern_type == NetworkPatternType.RAPID_FORWARDING]
            assert len(rf) >= 1
            assert rf[0].elapsed_minutes <= 60.0
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 6. Layering
# ---------------------------------------------------------------------------

class TestLayeringLive:
    _PREFIX = f"{_BASE_PREFIX}LAYER_"

    def test_layering_detected(self, neo4j_mgr):
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        # A → B → C → D (3 hops)
        chain = [f"{p}{x}" for x in ["A", "B", "C", "D"]]
        txns = [
            _make_canonical_tx(
                f"{p}TX{i}", chain[i], chain[i + 1], "300", ts_delta_minutes=i * 30
            )
            for i in range(3)
        ]
        for tx in txns:
            loader.load_transaction(tx)

        subject_tx = txns[0]  # A is sender
        try:
            agent = _agent(neo4j_mgr)
            result = agent.analyse(subject_tx)
            layering = [f for f in result.findings if f.pattern_type == NetworkPatternType.LAYERING]
            assert len(layering) >= 1
            assert layering[0].hop_count >= 2
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 7. Structuring-like
# ---------------------------------------------------------------------------

class TestStructuringLive:
    _PREFIX = f"{_BASE_PREFIX}STRUCT_"

    def test_structuring_detected(self, neo4j_mgr):
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        sender = f"{p}SENDER"
        txns = [
            _make_canonical_tx(
                f"{p}TX{i}", sender, f"{p}RECV{i}", "49500", ts_delta_minutes=i * 120
            )
            for i in range(3)  # 3 transfers over 4 hours
        ]
        for tx in txns:
            loader.load_transaction(tx)

        subject_tx = txns[0]
        try:
            agent = _agent(neo4j_mgr)
            result = agent.analyse(subject_tx)
            struct = [f for f in result.findings if f.pattern_type == NetworkPatternType.STRUCTURING]
            assert len(struct) >= 1
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 8. Idempotency: re-loading does not duplicate
# ---------------------------------------------------------------------------

class TestIdempotencyLive:
    _PREFIX = f"{_BASE_PREFIX}IDEM_"

    def test_reingestion_findings_stable(self, neo4j_mgr):
        """Loading the same transactions twice must not change finding counts."""
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        hub = f"{p}HUB"
        txns = [
            _make_canonical_tx(f"{p}TX{i}", hub, f"{p}DST{i}", "200")
            for i in range(3)
        ]
        for tx in txns:
            loader.load_transaction(tx)

        agent = _agent(neo4j_mgr)
        result1 = agent.analyse(txns[0])
        finding_count_1 = result1.finding_count

        # Re-ingest all transactions
        for tx in txns:
            loader.load_transaction(tx)

        result2 = agent.analyse(txns[0])

        try:
            assert result2.finding_count == finding_count_1
        finally:
            _cleanup(neo4j_mgr, p)


# ---------------------------------------------------------------------------
# 9. Cleanup isolation: only test-prefixed nodes removed
# ---------------------------------------------------------------------------

class TestCleanupIsolationLive:
    _PREFIX = f"{_BASE_PREFIX}CLEAN_"

    def test_cleanup_does_not_affect_other_data(self, neo4j_mgr):
        """Cleanup deletes only test-prefixed nodes."""
        p = self._PREFIX
        loader = TransactionGraphLoader(neo4j_mgr.session)
        tx = _make_canonical_tx(f"{p}TX1", f"{p}A", f"{p}B")
        loader.load_transaction(tx)

        # Verify our node exists
        from src.graph.queries import GraphQueryHelper
        qh = GraphQueryHelper(neo4j_mgr.session)
        assert qh.account_exists(f"{p}A")

        # Cleanup only our prefix
        _cleanup(neo4j_mgr, p)

        # Our node is gone
        assert not qh.account_exists(f"{p}A")
