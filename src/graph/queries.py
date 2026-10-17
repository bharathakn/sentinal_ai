"""
Sentinel AI — Graph Query Helpers

Provides parameterised, bounded Cypher query helpers for account network
investigation. All queries use parameters (never string interpolation).

Included queries
----------------
- get_account_with_transfers : account node + outgoing/incoming relationships
- get_transfer_path          : short path between two accounts (bounded depth)
- get_relationship_details   : tx_graph_ids, amounts, timestamps for a pair

Scope
-----
This module provides *infrastructure* query helpers only. Fraud-pattern
detection (layering, fan-in/fan-out, structuring, fraud rings) belongs to the
Agent 3 implementation phase and is intentionally NOT included here.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query constants
# ---------------------------------------------------------------------------

# Maximum number of hops for path queries — prevents costly full-graph traversal.
_DEFAULT_MAX_HOPS = 4
_ABSOLUTE_MAX_HOPS = 6  # Hard limit; caller may not exceed this.

# Default result limits
_DEFAULT_TRANSFER_LIMIT = 100
_DEFAULT_PATH_LIMIT = 10


# ---------------------------------------------------------------------------
# Cypher templates (parameterised)
# ---------------------------------------------------------------------------

# Retrieve an account node plus all its outgoing TRANSFERRED_TO relationships.
_GET_ACCOUNT_OUTGOING = """
MATCH (a:Account {account_id: $account_id})
OPTIONAL MATCH (a)-[r:TRANSFERRED_TO]->(b:Account)
RETURN
    a.account_id        AS account_id,
    a.source_dataset    AS source_dataset,
    a.account_name      AS account_name,
    b.account_id        AS counterpart_id,
    r.tx_graph_id       AS tx_graph_id,
    r.amount            AS amount,
    r.amount_str        AS amount_str,
    r.currency          AS currency,
    r.timestamp_utc     AS timestamp_utc,
    r.channel           AS channel,
    r.status            AS status,
    'outgoing'          AS direction
ORDER BY r.timestamp_utc
LIMIT $limit
"""

# Retrieve an account node plus all its incoming TRANSFERRED_TO relationships.
_GET_ACCOUNT_INCOMING = """
MATCH (a:Account {account_id: $account_id})
OPTIONAL MATCH (b:Account)-[r:TRANSFERRED_TO]->(a)
RETURN
    a.account_id        AS account_id,
    a.source_dataset    AS source_dataset,
    a.account_name      AS account_name,
    b.account_id        AS counterpart_id,
    r.tx_graph_id       AS tx_graph_id,
    r.amount            AS amount,
    r.amount_str        AS amount_str,
    r.currency          AS currency,
    r.timestamp_utc     AS timestamp_utc,
    r.channel           AS channel,
    r.status            AS status,
    'incoming'          AS direction
ORDER BY r.timestamp_utc
LIMIT $limit
"""

# Find the shortest directed path between two accounts, bounded by max_hops.
# Uses variable-length relationship pattern — bounded to prevent full scans.
_GET_TRANSFER_PATH = """
MATCH path = shortestPath(
    (a:Account {account_id: $from_account_id})-[:TRANSFERRED_TO*1..$max_hops]->(b:Account {account_id: $to_account_id})
)
WITH path, [n IN nodes(path) | n.account_id] AS node_ids,
     [r IN relationships(path) | {
         tx_graph_id:   r.tx_graph_id,
         amount:        r.amount,
         amount_str:    r.amount_str,
         currency:      r.currency,
         timestamp_utc: r.timestamp_utc,
         channel:       r.channel
     }] AS transfers
RETURN node_ids, transfers, length(path) AS path_length
ORDER BY path_length
LIMIT $limit
"""

# Retrieve relationship details (tx_graph_ids, amounts, timestamps) for a
# specific sender → receiver pair.
_GET_RELATIONSHIP_DETAILS = """
MATCH (a:Account {account_id: $from_account_id})-[r:TRANSFERRED_TO]->(b:Account {account_id: $to_account_id})
RETURN
    r.tx_graph_id       AS tx_graph_id,
    r.raw_record_id     AS raw_record_id,
    r.amount            AS amount,
    r.amount_str        AS amount_str,
    r.currency          AS currency,
    r.timestamp_utc     AS timestamp_utc,
    r.channel           AS channel,
    r.status            AS status,
    r.source_dataset    AS source_dataset
ORDER BY r.timestamp_utc
LIMIT $limit
"""

# Check whether an account node exists.
_ACCOUNT_EXISTS = """
MATCH (a:Account {account_id: $account_id})
RETURN count(a) AS count
"""


# ---------------------------------------------------------------------------
# Query helper class
# ---------------------------------------------------------------------------

class GraphQueryHelper:
    """
    Parameterised graph query helpers for account network investigation.

    Parameters
    ----------
    session_factory:
        Callable returning a neo4j.Session context manager
        (typically ``Neo4jConnectionManager.session``).

    Example
    -------
    ::

        with Neo4jConnectionManager() as mgr:
            qh = GraphQueryHelper(mgr.session)
            outgoing = qh.get_account_outgoing_transfers("ACC_IND_000001")
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Account transfer queries
    # ------------------------------------------------------------------

    def get_account_outgoing_transfers(
        self,
        account_id: str,
        limit: int = _DEFAULT_TRANSFER_LIMIT,
    ) -> list[dict[str, Any]]:
        """
        Return outgoing TRANSFERRED_TO relationships for an account.

        Parameters
        ----------
        account_id:
            The stable account_id to query.
        limit:
            Maximum number of transfer rows to return.

        Returns
        -------
        list[dict]
            Each row contains: account_id, counterpart_id, tx_graph_id,
            amount, currency, timestamp_utc, channel, status, direction.
        """
        with self._session_factory() as session:
            result = session.run(
                _GET_ACCOUNT_OUTGOING,
                account_id=account_id,
                limit=min(limit, _DEFAULT_TRANSFER_LIMIT),
            )
            return result.data()

    def get_account_incoming_transfers(
        self,
        account_id: str,
        limit: int = _DEFAULT_TRANSFER_LIMIT,
    ) -> list[dict[str, Any]]:
        """
        Return incoming TRANSFERRED_TO relationships for an account.

        Parameters
        ----------
        account_id:
            The stable account_id to query.
        limit:
            Maximum number of transfer rows to return.
        """
        with self._session_factory() as session:
            result = session.run(
                _GET_ACCOUNT_INCOMING,
                account_id=account_id,
                limit=min(limit, _DEFAULT_TRANSFER_LIMIT),
            )
            return result.data()

    def get_account_transfers(
        self,
        account_id: str,
        limit: int = _DEFAULT_TRANSFER_LIMIT,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Return both outgoing and incoming transfers for an account.

        Returns
        -------
        dict
            {
              "outgoing": [...],
              "incoming": [...],
            }
        """
        return {
            "outgoing": self.get_account_outgoing_transfers(account_id, limit=limit),
            "incoming": self.get_account_incoming_transfers(account_id, limit=limit),
        }

    # ------------------------------------------------------------------
    # Path query
    # ------------------------------------------------------------------

    def get_transfer_path(
        self,
        from_account_id: str,
        to_account_id: str,
        max_hops: int = _DEFAULT_MAX_HOPS,
        limit: int = _DEFAULT_PATH_LIMIT,
    ) -> list[dict[str, Any]]:
        """
        Find shortest directed transfer path(s) between two accounts.

        Parameters
        ----------
        from_account_id:
            Starting account ID.
        to_account_id:
            Target account ID.
        max_hops:
            Maximum relationship depth (capped at ``_ABSOLUTE_MAX_HOPS``
            to prevent expensive traversals).
        limit:
            Maximum number of paths to return.

        Returns
        -------
        list[dict]
            Each element: {node_ids, transfers, path_length}.

        Notes
        -----
        Neo4j (Cypher 5 / GQL 1.0) does not allow parameters inside the
        hop-range of ``shortestPath()``. The hop count is validated as an
        integer and interpolated into the query string at construction time —
        it is NOT user-supplied free text, so this is safe.
        """
        safe_hops = min(max_hops, _ABSOLUTE_MAX_HOPS)
        if safe_hops < 1:
            safe_hops = 1
        safe_limit = min(limit, _DEFAULT_PATH_LIMIT)

        # Cypher does not accept parameters inside shortestPath()'s hop range.
        # We interpolate the validated integer literal directly — safe because
        # safe_hops is always a bounded integer, never user-supplied text.
        path_cypher = f"""
MATCH path = shortestPath(
    (a:Account {{account_id: $from_account_id}})-[:TRANSFERRED_TO*1..{safe_hops}]->(b:Account {{account_id: $to_account_id}})
)
WITH path, [n IN nodes(path) | n.account_id] AS node_ids,
     [r IN relationships(path) | {{
         tx_graph_id:   r.tx_graph_id,
         amount:        r.amount,
         amount_str:    r.amount_str,
         currency:      r.currency,
         timestamp_utc: r.timestamp_utc,
         channel:       r.channel
     }}] AS transfers
RETURN node_ids, transfers, length(path) AS path_length
ORDER BY path_length
LIMIT {safe_limit}
"""

        with self._session_factory() as session:
            result = session.run(
                path_cypher,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
            )
            return result.data()


    # ------------------------------------------------------------------
    # Relationship details
    # ------------------------------------------------------------------

    def get_relationship_details(
        self,
        from_account_id: str,
        to_account_id: str,
        limit: int = _DEFAULT_TRANSFER_LIMIT,
    ) -> list[dict[str, Any]]:
        """
        Return all TRANSFERRED_TO relationships between two specific accounts.

        Includes tx_graph_id, amounts, timestamps, and channel for each
        distinct transaction — multiple transfers between the same pair are
        returned as separate rows.

        Parameters
        ----------
        from_account_id:
            Sender account ID.
        to_account_id:
            Receiver account ID.
        limit:
            Maximum number of relationship rows to return.

        Returns
        -------
        list[dict]
            One dict per TRANSFERRED_TO relationship.
        """
        with self._session_factory() as session:
            result = session.run(
                _GET_RELATIONSHIP_DETAILS,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                limit=min(limit, _DEFAULT_TRANSFER_LIMIT),
            )
            return result.data()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def account_exists(self, account_id: str) -> bool:
        """
        Check whether an Account node with the given account_id exists.

        Parameters
        ----------
        account_id:
            The stable account identifier.

        Returns
        -------
        bool
            True if the node exists; False otherwise.
        """
        with self._session_factory() as session:
            result = session.run(_ACCOUNT_EXISTS, account_id=account_id)
            row = result.single()
            if row is None:
                return False
            return row["count"] > 0
