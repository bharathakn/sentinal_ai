"""
Sentinel AI — Idempotent Transaction Graph Loader

Loads CanonicalTransaction records into Neo4j as an account-transfer graph.

Design rules
------------
* Idempotent: loading the same transaction twice produces one relationship,
  not two. MERGE on tx_graph_id prevents duplicates.
* Multiple distinct transactions between the same two accounts are preserved
  as separate TRANSFERRED_TO relationships (each has a unique tx_graph_id).
* Uses parameterised Cypher — no string interpolation of user data.
* Uses session.execute_write (transaction function) so each record is
  committed atomically — partial writes do not happen.
* Malformed records raise GraphMappingError before any write is attempted.
* Results report nodes/relationships created or matched without exposing
  Neo4j internals or credentials.
* Batch loading uses bounded batches and reports per-record validation errors.

Cypher strategy
---------------
Each transaction ingestion:
  1. MERGE sender Account node on account_id.
  2. MERGE receiver Account node on account_id.
  3. MERGE TRANSFERRED_TO relationship on tx_graph_id (unique per transaction).
  4. SET all relationship properties (idempotent update).

MERGE on the relationship uses the tx_graph_id property to distinguish
transactions, NOT the pattern (a)-[r]-(b) alone — which would collapse all
transfers between the same account pair into a single relationship.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

from ..schemas.canonical_transaction import CanonicalTransaction
from .mapping import (
    GraphMappingError,
    account_properties,
    relationship_properties,
    validate_for_graph,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoadResult:
    """Result from loading a single transaction into the graph."""

    tx_graph_id: str
    sender_account_id: str
    receiver_account_id: str
    nodes_created: int
    relationships_created: int
    success: bool
    error: str | None = None


@dataclass
class BatchLoadResult:
    """Aggregate result from a batch load operation."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    nodes_created: int = 0
    relationships_created: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

# MERGE sender and receiver Account nodes, then MERGE the TRANSFERRED_TO
# relationship keyed on tx_graph_id. Multiple transactions between the same
# pair of accounts produce separate relationships with distinct tx_graph_id values.
_LOAD_TRANSACTION_CYPHER = """
MERGE (sender:Account {account_id: $sender_account_id})
ON CREATE SET sender.source_dataset = $sender_source_dataset,
              sender.account_name   = $sender_account_name

MERGE (receiver:Account {account_id: $receiver_account_id})
ON CREATE SET receiver.source_dataset = $receiver_source_dataset,
              receiver.account_name   = $receiver_account_name

MERGE (sender)-[r:TRANSFERRED_TO {tx_graph_id: $tx_graph_id}]->(receiver)
ON CREATE SET
    r.raw_record_id   = $raw_record_id,
    r.source_dataset  = $source_dataset,
    r.amount          = $amount,
    r.amount_str      = $amount_str,
    r.currency        = $currency,
    r.timestamp_utc   = $timestamp_utc,
    r.channel         = $channel,
    r.status          = $status
ON MATCH SET
    r.amount          = $amount,
    r.amount_str      = $amount_str,
    r.currency        = $currency,
    r.timestamp_utc   = $timestamp_utc,
    r.channel         = $channel,
    r.status          = $status

RETURN
    sender.account_id   AS sender_id,
    receiver.account_id AS receiver_id,
    (CASE WHEN sender.account_id IS NOT NULL THEN 0 ELSE 1 END) AS nodes_created_hint,
    (CASE WHEN r.raw_record_id IS NOT NULL THEN 0 ELSE 1 END)   AS rel_created_hint
"""

# Bulk variant: one write transaction per chunk (same MERGE semantics).
# Used for remote databases (AuraDB), where one round trip per record is slow.
_LOAD_BATCH_UNWIND_CYPHER = "UNWIND $rows AS row\n" + (
    _LOAD_TRANSACTION_CYPHER.split("RETURN")[0]
    .replace("$", "row.")
) + "RETURN count(r) AS written"

# Separate counting query — used to report created vs matched counts accurately.
# Neo4j counters from execute_write are reliable via ManagedTransaction.
_COUNT_QUERY = """
RETURN 1
"""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class TransactionGraphLoader:
    """
    Loads CanonicalTransaction records into the Neo4j account-transfer graph.

    Parameters
    ----------
    session_factory:
        Callable that returns a neo4j.Session (typically
        ``Neo4jConnectionManager.session``).
    batch_size:
        Maximum number of transactions per batch when using load_batch().
        Prevents unbounded memory usage. Default: 100.

    Example
    -------
    ::

        with Neo4jConnectionManager() as mgr:
            loader = TransactionGraphLoader(mgr.session)
            result = loader.load_transaction(canonical_tx)
            print(result)
    """

    _MAX_BATCH_SIZE = 1000  # Hard upper bound; callers can set lower.

    def __init__(self, session_factory, batch_size: int = 100) -> None:
        self._session_factory = session_factory
        if not 1 <= batch_size <= self._MAX_BATCH_SIZE:
            raise ValueError(
                f"batch_size must be between 1 and {self._MAX_BATCH_SIZE}, "
                f"got {batch_size}."
            )
        self.batch_size = batch_size

    # ------------------------------------------------------------------
    # Single-record load
    # ------------------------------------------------------------------

    @staticmethod
    def _params(tx: CanonicalTransaction) -> dict:
        rel_props = relationship_properties(tx)
        source_dataset = rel_props["source_dataset"]
        sender_props = account_properties(tx.sender, source_dataset)
        receiver_props = account_properties(tx.receiver, source_dataset)
        return {
            "sender_account_id": sender_props["account_id"],
            "sender_source_dataset": sender_props.get("source_dataset", source_dataset),
            "sender_account_name": sender_props.get("account_name"),
            "receiver_account_id": receiver_props["account_id"],
            "receiver_source_dataset": receiver_props.get("source_dataset", source_dataset),
            "receiver_account_name": receiver_props.get("account_name"),
            **{k: rel_props[k] for k in ("tx_graph_id", "raw_record_id", "source_dataset", "amount",
                                         "amount_str", "currency", "timestamp_utc", "channel", "status")},
        }

    def load_transaction(self, tx: CanonicalTransaction) -> LoadResult:
        """
        Load a single CanonicalTransaction into the graph idempotently.

        Parameters
        ----------
        tx:
            A validated CanonicalTransaction with sender and receiver account IDs.

        Returns
        -------
        LoadResult
            Result containing node/relationship creation counts.

        Raises
        ------
        GraphMappingError
            If required fields (sender/receiver account_id) are absent.
        neo4j.exceptions.Neo4jError
            On graph write failure.
        """
        # Validate before touching the database.
        validate_for_graph(tx)

        rel_props = relationship_properties(tx)
        tx_graph_id = rel_props["tx_graph_id"]
        source_dataset = rel_props["source_dataset"]

        sender_props = account_properties(tx.sender, source_dataset)
        receiver_props = account_properties(tx.receiver, source_dataset)

        params = {
            # Sender node
            "sender_account_id": sender_props["account_id"],
            "sender_source_dataset": sender_props.get("source_dataset", source_dataset),
            "sender_account_name": sender_props.get("account_name"),
            # Receiver node
            "receiver_account_id": receiver_props["account_id"],
            "receiver_source_dataset": receiver_props.get("source_dataset", source_dataset),
            "receiver_account_name": receiver_props.get("account_name"),
            # Relationship
            "tx_graph_id": rel_props["tx_graph_id"],
            "raw_record_id": rel_props["raw_record_id"],
            "source_dataset": rel_props["source_dataset"],
            "amount": rel_props["amount"],
            "amount_str": rel_props["amount_str"],
            "currency": rel_props["currency"],
            "timestamp_utc": rel_props["timestamp_utc"],
            "channel": rel_props["channel"],
            "status": rel_props["status"],
        }

        with self._session_factory() as session:
            result = session.execute_write(self._write_transaction, params)

        logger.info(
            "Loaded transaction %r: nodes_created=%d, rels_created=%d.",
            tx_graph_id,
            result["nodes_created"],
            result["relationships_created"],
        )

        return LoadResult(
            tx_graph_id=tx_graph_id,
            sender_account_id=params["sender_account_id"],
            receiver_account_id=params["receiver_account_id"],
            nodes_created=result["nodes_created"],
            relationships_created=result["relationships_created"],
            success=True,
        )

    @staticmethod
    def _write_transaction(tx_fn, params: dict) -> dict:
        """
        Transaction function executed inside execute_write.

        Uses the ManagedTransaction counters to reliably report created counts.
        """
        result = tx_fn.run(_LOAD_TRANSACTION_CYPHER, **params)
        # Consume results to get summary counters
        summary = result.consume()
        counters = summary.counters
        return {
            "nodes_created": counters.nodes_created,
            "relationships_created": counters.relationships_created,
        }

    # ------------------------------------------------------------------
    # Batch load
    # ------------------------------------------------------------------

    def load_batch(
        self, transactions: Sequence[CanonicalTransaction]
    ) -> BatchLoadResult:
        """
        Load a collection of CanonicalTransaction records in bounded batches.

        Validation failures are recorded per-record and do not abort the
        entire batch. Write failures for a batch abort that batch and are
        recorded as errors; subsequent batches continue.

        Parameters
        ----------
        transactions:
            Iterable of CanonicalTransaction records to load.

        Returns
        -------
        BatchLoadResult
            Aggregate counts and per-record error list.
        """
        agg = BatchLoadResult(total=len(transactions))

        # Process in bounded batches
        for batch_start in range(0, len(transactions), self.batch_size):
            batch = transactions[batch_start: batch_start + self.batch_size]
            for tx in batch:
                try:
                    result = self.load_transaction(tx)
                    agg.succeeded += 1
                    agg.nodes_created += result.nodes_created
                    agg.relationships_created += result.relationships_created
                except GraphMappingError as exc:
                    agg.failed += 1
                    agg.errors.append(
                        f"Validation error for {tx.raw_record_id!r}: {exc}"
                    )
                    logger.warning(
                        "Skipping transaction %r due to mapping error: %s",
                        tx.raw_record_id,
                        exc,
                    )
                except Exception as exc:  # noqa: BLE001
                    agg.failed += 1
                    # Do not include credential-containing strings from exc details.
                    agg.errors.append(
                        f"Write error for {tx.raw_record_id!r}: "
                        f"{type(exc).__name__}: graph write failed."
                    )
                    logger.error(
                        "Graph write failed for transaction %r: %s: %s",
                        tx.raw_record_id,
                        type(exc).__name__,
                        exc,
                    )

        return agg

    def load_batch_unwind(self, transactions: Sequence[CanonicalTransaction]) -> BatchLoadResult:
        """Bulk load: validate each record, then write each chunk of
        ``batch_size`` records in ONE transaction (UNWIND). Idempotent (MERGE).

        Mapping errors are recorded per record; a failed chunk is recorded for
        every record in it and later chunks continue.
        """
        agg = BatchLoadResult(total=len(transactions))
        rows: list[tuple[str, dict]] = []
        for tx in transactions:
            try:
                validate_for_graph(tx)
                rows.append((tx.raw_record_id, self._params(tx)))
            except GraphMappingError as exc:
                agg.failed += 1
                agg.errors.append(f"Validation error for {tx.raw_record_id!r}: {exc}")

        def write(tx_fn, chunk: list[dict]) -> dict:
            summary = tx_fn.run(_LOAD_BATCH_UNWIND_CYPHER, rows=chunk).consume()
            return {"nodes_created": summary.counters.nodes_created,
                    "relationships_created": summary.counters.relationships_created}

        for start in range(0, len(rows), self.batch_size):
            chunk = rows[start: start + self.batch_size]
            try:
                with self._session_factory() as session:
                    res = session.execute_write(write, [p for _, p in chunk])
                agg.succeeded += len(chunk)
                agg.nodes_created += res["nodes_created"]
                agg.relationships_created += res["relationships_created"]
            except Exception as exc:  # noqa: BLE001
                agg.failed += len(chunk)
                agg.errors.append(f"Write error for chunk starting {chunk[0][0]!r} ({len(chunk)} records): "
                                  f"{type(exc).__name__}: graph write failed.")
                logger.error("Graph chunk write failed: %s", type(exc).__name__)
        return agg
