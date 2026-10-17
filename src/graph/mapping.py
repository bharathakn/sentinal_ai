"""
Sentinel AI — Graph Property Mapping

Maps CanonicalTransaction fields to Neo4j node/relationship properties.

Design rules
------------
* Only explicitly allowlisted properties are written to the graph.
* No personal information beyond stable account IDs is stored.
* All values are validated and normalised before being passed to Cypher.
* Missing optional fields produce None (not fabricated defaults).
* Timestamps are normalised to UTC ISO-8601 strings.
* Amounts are stored as floats (Neo4j has no Decimal type); the
  original string representation is preserved as amount_str for fidelity.
* The transaction idempotency key (tx_graph_id) is derived from the
  stable raw_record_id and source_dataset — never from random data.

Graph property keys
-------------------

Account node
  account_id       : str   — stable account identifier (required)
  source_dataset   : str   — originating dataset name
  account_name     : str   — optional, from AccountInfo.account_name

TRANSFERRED_TO relationship
  tx_graph_id      : str   — idempotency key; raw_record_id::source_dataset
  raw_record_id    : str   — original record identifier
  source_dataset   : str   — originating dataset
  amount           : float — transaction amount
  amount_str       : str   — amount as decimal string (preserves precision)
  currency         : str   — ISO-4217 currency code
  timestamp_utc    : str   — UTC ISO-8601 timestamp string (or None)
  channel          : str   — payment channel enum value
  status           : str   — transaction status enum value
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from ..schemas.canonical_transaction import CanonicalTransaction, AccountInfo


# ---------------------------------------------------------------------------
# Idempotency key
# ---------------------------------------------------------------------------

def make_tx_graph_id(tx: CanonicalTransaction) -> str:
    """
    Build a stable graph idempotency key for a transaction.

    Format: ``<raw_record_id>::<source_dataset>``

    This key is used in MERGE on TRANSFERRED_TO relationships to prevent
    duplicate relationship creation on repeated ingestion of the same record.

    The key is deterministic and based solely on stable source-record fields.
    """
    return f"{tx.raw_record_id}::{tx.source_dataset}"


# ---------------------------------------------------------------------------
# Timestamp normalisation
# ---------------------------------------------------------------------------

def _normalise_timestamp(ts: Optional[datetime]) -> Optional[str]:
    """Convert a datetime to a UTC ISO-8601 string, or None if absent."""
    if ts is None:
        return None
    # If naive, assume UTC; if aware, convert to UTC.
    if ts.tzinfo is None:
        ts_utc = ts.replace(tzinfo=timezone.utc)
    else:
        ts_utc = ts.astimezone(timezone.utc)
    return ts_utc.isoformat()


# ---------------------------------------------------------------------------
# Account node properties
# ---------------------------------------------------------------------------

def account_properties(account: AccountInfo, source_dataset: str) -> Optional[dict[str, Any]]:
    """
    Extract Neo4j-ready properties for an Account node.

    Returns
    -------
    dict | None
        None if account_id is absent (cannot create a stable node).
    """
    account_id = account.account_id
    if not account_id or not account_id.strip():
        return None

    props: dict[str, Any] = {
        "account_id": account_id.strip(),
        "source_dataset": source_dataset,
    }

    # Optional: account_name (PaySim provides this; other sources may not)
    if account.account_name:
        props["account_name"] = account.account_name.strip()

    return props


# ---------------------------------------------------------------------------
# Relationship properties
# ---------------------------------------------------------------------------

def relationship_properties(tx: CanonicalTransaction) -> dict[str, Any]:
    """
    Extract Neo4j-ready properties for a TRANSFERRED_TO relationship.

    The returned dict is safe to pass as Cypher parameters. All values
    are Python primitives (str, float, None) — no Decimal or datetime objects.

    Parameters
    ----------
    tx:
        A validated CanonicalTransaction.

    Returns
    -------
    dict
        Graph relationship properties with the tx_graph_id idempotency key.
    """
    # Amount: store as float for Neo4j native numeric queries and as str
    # for precision-preserving reads.
    amount_decimal: Decimal = tx.amount
    amount_float = float(amount_decimal)
    amount_str = str(amount_decimal)

    # Timestamp: normalise to UTC ISO string
    ts_utc = _normalise_timestamp(tx.timestamp)

    # Channel and status as string values (enum .value)
    channel_val = tx.channel if isinstance(tx.channel, str) else tx.channel.value
    status_val = tx.status if isinstance(tx.status, str) else tx.status.value

    source_dataset = (
        tx.source_dataset
        if isinstance(tx.source_dataset, str)
        else tx.source_dataset.value
    )

    return {
        "tx_graph_id": make_tx_graph_id(tx),
        "raw_record_id": tx.raw_record_id,
        "source_dataset": source_dataset,
        "amount": amount_float,
        "amount_str": amount_str,
        "currency": tx.currency,
        "timestamp_utc": ts_utc,
        "channel": channel_val,
        "status": status_val,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class GraphMappingError(ValueError):
    """Raised when a CanonicalTransaction cannot be mapped to graph properties."""


def validate_for_graph(tx: CanonicalTransaction) -> None:
    """
    Validate that a CanonicalTransaction has the minimum required fields
    for graph ingestion.

    Raises
    ------
    GraphMappingError
        If sender account_id or receiver account_id is missing.
    """
    if not tx.sender.account_id or not tx.sender.account_id.strip():
        raise GraphMappingError(
            f"Transaction {tx.raw_record_id!r}: sender.account_id is required "
            "for graph ingestion but is absent or empty."
        )
    if not tx.receiver.account_id or not tx.receiver.account_id.strip():
        raise GraphMappingError(
            f"Transaction {tx.raw_record_id!r}: receiver.account_id is required "
            "for graph ingestion but is absent or empty."
        )
    if tx.amount < Decimal("0"):
        raise GraphMappingError(
            f"Transaction {tx.raw_record_id!r}: amount must be >= 0."
        )
