"""
Sentinel AI — Phase 7 Integration Test: Neo4j Graph Infrastructure

This test creates a deterministic small graph via the real graph loader when
a Neo4j instance is explicitly configured (NEO4J_URI set in environment).

Scenario
--------
Account A → ₹1,000  → Account B  (TXN_INTEG_001)
Account B → ₹400    → Account C  (TXN_INTEG_002)
Account A → ₹250    → Account B  (TXN_INTEG_003) — second distinct A→B transfer

Verifications
-------------
- All three Account nodes (A, B, C) exist.
- Three TRANSFERRED_TO relationships exist.
- Relationships have correct direction and amounts.
- Re-ingesting the same records does not create duplicates.
- A query can retrieve the A → B → C transfer path.
- Cleanup removes only the test-prefixed nodes (no collateral damage).

Skip policy
-----------
All tests are skipped when NEO4J_URI is not configured. The skip message
clearly states that live graph integration was NOT executed, as required.

Test isolation
--------------
Uses account IDs with a unique prefix (INTEG_TEST_) to avoid colliding with
any existing production/development data. Cleanup deletes only nodes bearing
this prefix.

WARNING: Do not run this test against a production database containing real data.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
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
from src.graph.queries import GraphQueryHelper

# ---------------------------------------------------------------------------
# Skip guard — skip all tests when no Neo4j is configured
# ---------------------------------------------------------------------------

_NEO4J_CONFIGURED = bool(
    os.environ.get("NEO4J_URI", "").strip()
    and os.environ.get("NEO4J_USERNAME", "").strip()
    and os.environ.get("NEO4J_PASSWORD", "").strip()
)

pytestmark = pytest.mark.skipif(
    not _NEO4J_CONFIGURED,
    reason=(
        "Live Neo4j integration tests skipped: NEO4J_URI / NEO4J_USERNAME / "
        "NEO4J_PASSWORD are not configured. All offline unit tests ran instead. "
        "Set these environment variables and re-run to execute live graph tests."
    ),
)

# ---------------------------------------------------------------------------
# Test account IDs — unique prefix prevents collateral damage during cleanup
# ---------------------------------------------------------------------------

_PREFIX = "INTEG_TEST_"
_ACCOUNT_A = f"{_PREFIX}ACCOUNT_A"
_ACCOUNT_B = f"{_PREFIX}ACCOUNT_B"
_ACCOUNT_C = f"{_PREFIX}ACCOUNT_C"

_TXN_1 = f"{_PREFIX}TXN_001"  # A → B  ₹1000
_TXN_2 = f"{_PREFIX}TXN_002"  # B → C  ₹400
_TXN_3 = f"{_PREFIX}TXN_003"  # A → B  ₹250  (second distinct A→B transfer)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def neo4j_manager():
    """Module-scoped Neo4j connection manager for integration tests."""
    mgr = Neo4jConnectionManager()
    mgr.connect()
    mgr.verify_connectivity()
    yield mgr
    mgr.close()


@pytest.fixture(scope="module")
def schema_mgr(neo4j_manager):
    return GraphSchemaManager(neo4j_manager.session)


@pytest.fixture(scope="module")
def loader(neo4j_manager):
    return TransactionGraphLoader(neo4j_manager.session)


@pytest.fixture(scope="module")
def query_helper(neo4j_manager):
    return GraphQueryHelper(neo4j_manager.session)


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown(neo4j_manager, schema_mgr, loader):
    """
    Setup: initialise schema and load deterministic test data.
    Teardown: delete only test-prefixed nodes (no collateral damage).
    """
    # Setup
    schema_mgr.init_schema()
    _load_test_transactions(loader)
    yield
    # Teardown — restrict cleanup to test-prefixed nodes only
    _cleanup_test_data(neo4j_manager)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def _make_test_tx(
    raw_record_id: str,
    sender_id: str,
    receiver_id: str,
    amount_str: str,
) -> CanonicalTransaction:
    return CanonicalTransaction(
        raw_record_id=raw_record_id,
        source_dataset=DataSource.INDIA_SYNTHETIC,
        amount=Decimal(amount_str),
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
        channel=TransactionChannel.UPI,
        status=TransactionStatus.SUCCESS,
        sender=AccountInfo(account_id=sender_id),
        receiver=AccountInfo(account_id=receiver_id),
    )


def _load_test_transactions(loader: TransactionGraphLoader) -> None:
    tx1 = _make_test_tx(_TXN_1, _ACCOUNT_A, _ACCOUNT_B, "1000.00")
    tx2 = _make_test_tx(_TXN_2, _ACCOUNT_B, _ACCOUNT_C, "400.00")
    tx3 = _make_test_tx(_TXN_3, _ACCOUNT_A, _ACCOUNT_B, "250.00")
    for tx in [tx1, tx2, tx3]:
        loader.load_transaction(tx)


def _cleanup_test_data(mgr: Neo4jConnectionManager) -> None:
    """Delete only test-prefixed Account nodes and their relationships."""
    cleanup_cypher = """
    MATCH (a:Account)
    WHERE a.account_id STARTS WITH $prefix
    DETACH DELETE a
    """
    with mgr.session() as session:
        session.run(cleanup_cypher, prefix=_PREFIX)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestAccountNodesExist:
    """All three Account nodes must exist after loading."""

    def test_account_a_exists(self, query_helper):
        assert query_helper.account_exists(_ACCOUNT_A), \
            f"Account node {_ACCOUNT_A!r} not found in graph."

    def test_account_b_exists(self, query_helper):
        assert query_helper.account_exists(_ACCOUNT_B), \
            f"Account node {_ACCOUNT_B!r} not found in graph."

    def test_account_c_exists(self, query_helper):
        assert query_helper.account_exists(_ACCOUNT_C), \
            f"Account node {_ACCOUNT_C!r} not found in graph."


class TestRelationshipDirectionAndAmounts:
    """Relationships must have correct direction and amounts."""

    def test_a_to_b_transfers_exist(self, query_helper):
        transfers = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        assert len(transfers) == 2, \
            f"Expected 2 A→B transfers, found {len(transfers)}: {transfers}"

    def test_b_to_c_transfer_exists(self, query_helper):
        transfers = query_helper.get_relationship_details(_ACCOUNT_B, _ACCOUNT_C)
        assert len(transfers) == 1, \
            f"Expected 1 B→C transfer, found {len(transfers)}: {transfers}"

    def test_a_to_b_amounts_correct(self, query_helper):
        transfers = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        amounts = sorted([t["amount"] for t in transfers])
        assert amounts == pytest.approx([250.0, 1000.0]), \
            f"Unexpected amounts: {amounts}"

    def test_b_to_c_amount_correct(self, query_helper):
        transfers = query_helper.get_relationship_details(_ACCOUNT_B, _ACCOUNT_C)
        assert transfers[0]["amount"] == pytest.approx(400.0)

    def test_direction_not_reversed(self, query_helper):
        """B→A should return no transfers (direction must be preserved)."""
        transfers = query_helper.get_relationship_details(_ACCOUNT_B, _ACCOUNT_A)
        assert len(transfers) == 0, \
            f"Expected 0 B→A transfers (wrong direction), found {len(transfers)}"

    def test_timestamps_present(self, query_helper):
        transfers = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        for t in transfers:
            assert t["timestamp_utc"] is not None, \
                f"Missing timestamp_utc on transfer: {t}"

    def test_currency_is_inr(self, query_helper):
        transfers = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        for t in transfers:
            assert t["currency"] == "INR"


class TestThreeDistinctTransactions:
    """All three transactions must remain separate (not collapsed)."""

    def test_total_relationships_on_outgoing_a(self, query_helper):
        outgoing = query_helper.get_account_outgoing_transfers(_ACCOUNT_A)
        # Filter to only test-prefixed counterparts
        test_outgoing = [
            r for r in outgoing
            if r.get("counterpart_id", "").startswith(_PREFIX)
        ]
        assert len(test_outgoing) == 2, \
            f"Expected 2 outgoing transfers from A, got {len(test_outgoing)}"

    def test_all_tx_graph_ids_are_distinct(self, query_helper):
        ab = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        bc = query_helper.get_relationship_details(_ACCOUNT_B, _ACCOUNT_C)
        all_ids = [r["tx_graph_id"] for r in ab + bc]
        assert len(all_ids) == len(set(all_ids)), \
            f"Duplicate tx_graph_ids found: {all_ids}"

    def test_tx_graph_ids_contain_raw_record_ids(self, query_helper):
        ab = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        raw_ids_in_graph = [r.get("raw_record_id") for r in ab]
        assert _TXN_1 in raw_ids_in_graph or _TXN_3 in raw_ids_in_graph


class TestIdempotentReIngestion:
    """Re-ingesting the same records must not create duplicates."""

    def test_reingestion_does_not_duplicate_a_to_b(self, loader, query_helper):
        # Re-ingest transaction 1 (A→B ₹1000)
        tx1 = _make_test_tx(_TXN_1, _ACCOUNT_A, _ACCOUNT_B, "1000.00")
        loader.load_transaction(tx1)

        # Still exactly 2 A→B transfers
        transfers = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        assert len(transfers) == 2, \
            f"Duplicate detected after re-ingestion: {len(transfers)} A→B transfers found."

    def test_reingestion_full_batch(self, loader, query_helper):
        """Re-loading all three records must leave counts unchanged."""
        tx1 = _make_test_tx(_TXN_1, _ACCOUNT_A, _ACCOUNT_B, "1000.00")
        tx2 = _make_test_tx(_TXN_2, _ACCOUNT_B, _ACCOUNT_C, "400.00")
        tx3 = _make_test_tx(_TXN_3, _ACCOUNT_A, _ACCOUNT_B, "250.00")
        loader.load_batch([tx1, tx2, tx3])

        ab = query_helper.get_relationship_details(_ACCOUNT_A, _ACCOUNT_B)
        bc = query_helper.get_relationship_details(_ACCOUNT_B, _ACCOUNT_C)
        assert len(ab) == 2
        assert len(bc) == 1


class TestTransferPathQuery:
    """A → B → C path must be retrievable via the path query."""

    def test_path_a_to_c_exists(self, query_helper):
        paths = query_helper.get_transfer_path(
            from_account_id=_ACCOUNT_A,
            to_account_id=_ACCOUNT_C,
            max_hops=3,
        )
        assert len(paths) > 0, "No A→C path found; expected A→B→C."

    def test_path_includes_b_as_intermediate(self, query_helper):
        paths = query_helper.get_transfer_path(
            from_account_id=_ACCOUNT_A,
            to_account_id=_ACCOUNT_C,
            max_hops=3,
        )
        assert len(paths) > 0
        node_ids = paths[0]["node_ids"]
        assert _ACCOUNT_B in node_ids, \
            f"Account B not in path nodes: {node_ids}"

    def test_path_length_is_two_hops(self, query_helper):
        paths = query_helper.get_transfer_path(
            from_account_id=_ACCOUNT_A,
            to_account_id=_ACCOUNT_C,
            max_hops=3,
        )
        assert len(paths) > 0
        assert paths[0]["path_length"] == 2


class TestSchemaIdempotency:
    """Schema init can be called repeatedly without error."""

    def test_schema_init_twice(self, schema_mgr):
        schema_mgr.init_schema()
        schema_mgr.init_schema()  # must not raise

    def test_schema_info_returns_positive_counts(self, schema_mgr):
        info = schema_mgr.schema_info()
        assert info["constraints"] >= 1
        assert info["indexes"] >= 1
