"""
Sentinel AI — Agent 3: Network Analyser

Analyses account-transfer relationships in Neo4j and produces structured,
evidence-backed findings for downstream Agent 4 risk assessment.

Agent 3 is the third stage of the Sentinel AI investigation pipeline:

    Agent 1 (Anomaly Detector) → Agent 2 (Evidence Gatherer)
    → Agent 3 (Network Analyser) → Agent 4 (Risk Assessor) [future]

Design rules
------------
* Reuses Phase 7 graph infrastructure (connection, loader, queries, schema).
* Ingests the subject transaction idempotently if required.
* Does NOT create a competing Neo4j connection layer.
* All pattern detectors are isolated in detectors.py and independently testable.
* Graph failures are reported explicitly — never silently converted into a
  clean analysis result.
* Credentials and connection strings are never included in log messages or errors.
* This agent does NOT produce a final risk score — that is Agent 4's role.

Pipeline integration
--------------------
Consumes:
    transaction    : CanonicalTransaction (required)
    agent1_output  : Agent1Output (optional — passed through for correlation)
    agent2_output  : Agent2Output (optional — passed through for correlation)

Produces:
    Agent3Output in SentinelState["agent3_output"]

LangGraph compatibility
-----------------------
The agent is callable as a LangGraph node:
    state -> state

It is compatible with SentinelState TypedDict without requiring LangGraph
to be installed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ...schemas.canonical_transaction import CanonicalTransaction
from ...graph.connection import (
    Neo4jConnectionManager,
    Neo4jConfigError,
    Neo4jAuthError,
    Neo4jConnectivityError,
)
from ...graph.loader import TransactionGraphLoader
from ...graph.queries import GraphQueryHelper
from ...graph.schema import GraphSchemaManager

from .config import Agent3Config
from .detectors import (
    detect_fan_in,
    detect_fan_out,
    detect_layering,
    detect_mule_like,
    detect_rapid_forwarding,
    detect_structuring,
    detect_suspicious_cluster,
)
from .output_schema import (
    Agent3Output,
    Agent3Status,
    NetworkFinding,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cluster neighbourhood query
# ---------------------------------------------------------------------------

_CLUSTER_NEIGHBOURHOOD = """
MATCH (subject:Account {{account_id: $account_id}})
MATCH (subject)-[r1:TRANSFERRED_TO]->(neighbor:Account)
OPTIONAL MATCH (neighbor)-[r2:TRANSFERRED_TO]->(neighbor2:Account)
WHERE id(neighbor2) <> id(subject)
WITH
    subject, neighbor, neighbor2, r1, r2
RETURN DISTINCT
    subject.account_id      AS from_id,
    neighbor.account_id     AS to_id,
    r1.tx_graph_id          AS tx_graph_id,
    r1.raw_record_id        AS raw_record_id,
    r1.amount               AS amount,
    r1.amount_str           AS amount_str,
    r1.currency             AS currency,
    r1.timestamp_utc        AS timestamp_utc,
    r1.channel              AS channel
LIMIT {limit}
UNION
MATCH (subject:Account {{account_id: $account_id}})
MATCH (neighbor:Account)-[r1:TRANSFERRED_TO]->(subject)
RETURN DISTINCT
    neighbor.account_id     AS from_id,
    subject.account_id      AS to_id,
    r1.tx_graph_id          AS tx_graph_id,
    r1.raw_record_id        AS raw_record_id,
    r1.amount               AS amount,
    r1.amount_str           AS amount_str,
    r1.currency             AS currency,
    r1.timestamp_utc        AS timestamp_utc,
    r1.channel              AS channel
LIMIT {limit}
"""

_LAYERING_MULTI_HOP = """
MATCH path = (sender:Account {{account_id: $sender_id}})-[:TRANSFERRED_TO*{min_hops}..{max_hops}]->(receiver:Account)
WHERE receiver.account_id <> $sender_id
WITH path,
     [n IN nodes(path) | n.account_id] AS node_ids,
     [r IN relationships(path) | {{
         tx_graph_id:   r.tx_graph_id,
         amount:        r.amount,
         amount_str:    r.amount_str,
         currency:      r.currency,
         timestamp_utc: r.timestamp_utc,
         channel:       r.channel
     }}] AS transfers
RETURN node_ids, transfers, length(path) AS path_length
ORDER BY path_length DESC
LIMIT {limit}
"""


class NetworkAnalyserAgent:
    """
    Agent 3: Network Analyser for the Sentinel AI investigation pipeline.

    Analyses account-transfer relationships in Neo4j for the seven supported
    network patterns and returns structured, evidence-backed findings.

    Parameters
    ----------
    config:
        Agent3Config instance. If None, uses Agent3Config.from_env().
    connection_manager:
        Optional pre-built Neo4jConnectionManager for testing/reuse.
        If None, the agent creates and manages its own connection.

    Example
    -------
    ::

        agent = NetworkAnalyserAgent()
        state = {"transaction": tx, "agent1_output": a1_out, "agent2_output": a2_out}
        updated_state = agent(state)
        output = updated_state["agent3_output"]
    """

    def __init__(
        self,
        config: Optional[Agent3Config] = None,
        connection_manager: Optional[Neo4jConnectionManager] = None,
    ) -> None:
        self._config = config or Agent3Config.from_env()
        self._external_manager = connection_manager

    # ------------------------------------------------------------------
    # LangGraph-compatible callable interface
    # ------------------------------------------------------------------

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph-compatible node function.

        Reads from SentinelState, runs Agent 3, writes agent3_output.
        Preserves all existing state fields unmodified.

        Parameters
        ----------
        state:
            SentinelState dict. Must contain "transaction".

        Returns
        -------
        dict
            Updated state with "agent3_output" added.
        """
        transaction: Optional[CanonicalTransaction] = state.get("transaction")

        if transaction is None:
            return {
                **state,
                "agent3_output": self._make_error_output(
                    error="No transaction provided in pipeline state.",
                    status=Agent3Status.VALIDATION_ERROR,
                ),
            }

        agent1_output = state.get("agent1_output")
        agent2_output = state.get("agent2_output")

        output = self.analyse(
            transaction=transaction,
            agent1_output=agent1_output,
            agent2_output=agent2_output,
        )

        return {**state, "agent3_output": output}

    # ------------------------------------------------------------------
    # Main analysis method (also callable directly for testing)
    # ------------------------------------------------------------------

    def analyse(
        self,
        transaction: CanonicalTransaction,
        agent1_output: Any = None,
        agent2_output: Any = None,
    ) -> Agent3Output:
        """
        Run all network-pattern detectors against the Neo4j graph.

        Parameters
        ----------
        transaction:
            The canonical transaction being investigated.
        agent1_output:
            Agent 1 output (for correlation IDs only). Optional.
        agent2_output:
            Agent 2 output (for correlation IDs only). Optional.

        Returns
        -------
        Agent3Output
        """
        sender_id = (
            transaction.sender.account_id if transaction.sender else None
        )
        receiver_id = (
            transaction.receiver.account_id if transaction.receiver else None
        )

        if not sender_id or not receiver_id:
            return self._make_error_output(
                error=(
                    "Transaction is missing sender or receiver account_id. "
                    f"sender_account_id={'present' if sender_id else 'MISSING'}, "
                    f"receiver_account_id={'present' if receiver_id else 'MISSING'}."
                ),
                status=Agent3Status.VALIDATION_ERROR,
                transaction=transaction,
                agent1_output=agent1_output,
                agent2_output=agent2_output,
            )

        # Try to connect
        if self._external_manager is not None:
            return self._run_with_manager(
                self._external_manager,
                transaction=transaction,
                sender_id=sender_id,
                receiver_id=receiver_id,
                agent1_output=agent1_output,
                agent2_output=agent2_output,
            )

        try:
            mgr = Neo4jConnectionManager()
            mgr.connect()
            mgr.verify_connectivity()
        except Neo4jConfigError as exc:
            return self._make_error_output(
                error=f"Neo4j not configured: {exc}",
                status=Agent3Status.UNAVAILABLE,
                transaction=transaction,
                agent1_output=agent1_output,
                agent2_output=agent2_output,
            )
        except (Neo4jAuthError, Neo4jConnectivityError) as exc:
            return self._make_error_output(
                error=f"Neo4j unreachable: {type(exc).__name__}",
                status=Agent3Status.UNAVAILABLE,
                transaction=transaction,
                agent1_output=agent1_output,
                agent2_output=agent2_output,
            )
        except Exception as exc:  # noqa: BLE001
            return self._make_error_output(
                error=f"Unexpected graph connection error: {type(exc).__name__}",
                status=Agent3Status.FAILED,
                transaction=transaction,
                agent1_output=agent1_output,
                agent2_output=agent2_output,
            )

        try:
            return self._run_with_manager(
                mgr,
                transaction=transaction,
                sender_id=sender_id,
                receiver_id=receiver_id,
                agent1_output=agent1_output,
                agent2_output=agent2_output,
            )
        finally:
            try:
                mgr.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Analysis with an established connection
    # ------------------------------------------------------------------

    def _run_with_manager(
        self,
        mgr: Neo4jConnectionManager,
        *,
        transaction: CanonicalTransaction,
        sender_id: str,
        receiver_id: str,
        agent1_output: Any,
        agent2_output: Any,
    ) -> Agent3Output:
        """Run all detectors with an established Neo4j connection."""
        findings: list[NetworkFinding] = []
        warnings: list[str] = []
        errors: list[str] = []
        detectors_run: list[str] = []
        detectors_skipped: list[str] = []

        # ------------------------------------------------------------------
        # Step 1: Idempotently ingest the subject transaction
        # ------------------------------------------------------------------
        graph_ingestion_performed = False
        try:
            loader = TransactionGraphLoader(mgr.session, batch_size=1)
            loader.load_transaction(transaction)
            graph_ingestion_performed = True
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"Graph ingestion warning: {type(exc).__name__}. "
                "Proceeding with existing graph data."
            )

        # ------------------------------------------------------------------
        # Step 2: Resolve graph state (account existence)
        # ------------------------------------------------------------------
        qh = GraphQueryHelper(mgr.session)

        try:
            sender_in_graph = qh.account_exists(sender_id)
            receiver_in_graph = qh.account_exists(receiver_id)
        except Exception as exc:  # noqa: BLE001
            return self._make_error_output(
                error=f"Graph existence check failed: {type(exc).__name__}",
                status=Agent3Status.FAILED,
                transaction=transaction,
                agent1_output=agent1_output,
                agent2_output=agent2_output,
                graph_ingestion_performed=graph_ingestion_performed,
            )

        if not sender_in_graph and not receiver_in_graph:
            return Agent3Output(
                transaction_id=transaction.raw_record_id,
                source_dataset=str(transaction.source_dataset) if transaction.source_dataset else None,
                sender_account_id=sender_id,
                receiver_account_id=receiver_id,
                status=Agent3Status.UNAVAILABLE,
                warnings=["Neither sender nor receiver account found in Neo4j graph."],
                errors=[],
                detectors_run=[],
                detectors_skipped=_all_detector_names(),
                sender_in_graph=False,
                receiver_in_graph=False,
                graph_ingestion_performed=graph_ingestion_performed,
                findings=[],
                finding_count=0,
                agent1_output_ref=_get_output_ref(agent1_output),
                agent2_output_ref=_get_output_ref(agent2_output),
            )

        # ------------------------------------------------------------------
        # Step 3: Fetch graph data for the primary accounts
        # ------------------------------------------------------------------
        limit = self._config.transfer_query_limit
        primary_id = sender_id

        outgoing: list[dict] = []
        incoming: list[dict] = []
        cluster_rows: list[dict] = []
        paths: list[dict] = []

        try:
            outgoing = qh.get_account_outgoing_transfers(primary_id, limit=limit)
            detectors_run.append("graph_fetch_outgoing")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Outgoing transfer query failed: {type(exc).__name__}")
            detectors_skipped.extend(["STRUCTURING", "FAN_OUT", "RAPID_FORWARDING", "MULE_LIKE"])

        try:
            incoming = qh.get_account_incoming_transfers(primary_id, limit=limit)
            detectors_run.append("graph_fetch_incoming")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Incoming transfer query failed: {type(exc).__name__}")
            detectors_skipped.extend(["FAN_IN", "RAPID_FORWARDING", "MULE_LIKE"])

        # Cluster neighbourhood
        try:
            cluster_rows = self._query_cluster_neighbourhood(mgr, primary_id)
            detectors_run.append("graph_fetch_cluster")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Cluster neighbourhood query failed: {type(exc).__name__}")
            detectors_skipped.append("SUSPICIOUS_CLUSTER")

        # Layering paths
        try:
            paths = self._query_layering_paths(mgr, primary_id)
            detectors_run.append("graph_fetch_paths")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Layering path query failed: {type(exc).__name__}")
            detectors_skipped.append("LAYERING")

        # ------------------------------------------------------------------
        # Step 4: Run detectors
        # ------------------------------------------------------------------

        # A. Layering
        if "LAYERING" not in detectors_skipped:
            try:
                f = detect_layering(paths, primary_id, self._config)
                findings.extend(f)
                detectors_run.append("LAYERING")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"LAYERING detector error: {type(exc).__name__}")
                detectors_skipped.append("LAYERING")

        # B. Structuring
        if "STRUCTURING" not in detectors_skipped and outgoing:
            try:
                f = detect_structuring(outgoing, primary_id, self._config)
                findings.extend(f)
                detectors_run.append("STRUCTURING")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"STRUCTURING detector error: {type(exc).__name__}")
                detectors_skipped.append("STRUCTURING")

        # C. Fan-in
        if "FAN_IN" not in detectors_skipped and incoming:
            try:
                f = detect_fan_in(incoming, primary_id, self._config)
                findings.extend(f)
                detectors_run.append("FAN_IN")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"FAN_IN detector error: {type(exc).__name__}")
                detectors_skipped.append("FAN_IN")

        # D. Fan-out
        if "FAN_OUT" not in detectors_skipped and outgoing:
            try:
                f = detect_fan_out(outgoing, primary_id, self._config)
                findings.extend(f)
                detectors_run.append("FAN_OUT")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"FAN_OUT detector error: {type(exc).__name__}")
                detectors_skipped.append("FAN_OUT")

        # E. Mule-like
        if not any(d in detectors_skipped for d in ["FAN_IN", "FAN_OUT"]):
            try:
                f = detect_mule_like(incoming, outgoing, primary_id, self._config)
                findings.extend(f)
                detectors_run.append("MULE_LIKE")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"MULE_LIKE detector error: {type(exc).__name__}")
                detectors_skipped.append("MULE_LIKE")

        # F. Rapid forwarding
        if "RAPID_FORWARDING" not in detectors_skipped:
            try:
                f = detect_rapid_forwarding(incoming, outgoing, primary_id, self._config)
                findings.extend(f)
                detectors_run.append("RAPID_FORWARDING")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"RAPID_FORWARDING detector error: {type(exc).__name__}")
                detectors_skipped.append("RAPID_FORWARDING")

        # G. Suspicious cluster
        if "SUSPICIOUS_CLUSTER" not in detectors_skipped:
            try:
                f = detect_suspicious_cluster(cluster_rows, primary_id, self._config)
                findings.extend(f)
                detectors_run.append("SUSPICIOUS_CLUSTER")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"SUSPICIOUS_CLUSTER detector error: {type(exc).__name__}")
                detectors_skipped.append("SUSPICIOUS_CLUSTER")

        # ------------------------------------------------------------------
        # Step 5: Assemble output
        # ------------------------------------------------------------------
        status = (
            Agent3Status.PARTIAL
            if detectors_skipped
            else Agent3Status.COMPLETE
        )

        return Agent3Output(
            transaction_id=transaction.raw_record_id,
            source_dataset=(
                str(transaction.source_dataset)
                if transaction.source_dataset
                else None
            ),
            sender_account_id=sender_id,
            receiver_account_id=receiver_id,
            status=status,
            warnings=warnings,
            errors=errors,
            detectors_run=list(dict.fromkeys(detectors_run)),
            detectors_skipped=list(dict.fromkeys(detectors_skipped)),
            sender_in_graph=sender_in_graph,
            receiver_in_graph=receiver_in_graph,
            graph_ingestion_performed=graph_ingestion_performed,
            findings=findings,
            finding_count=len(findings),
            agent1_output_ref=_get_output_ref(agent1_output),
            agent2_output_ref=_get_output_ref(agent2_output),
        )

    # ------------------------------------------------------------------
    # Graph queries specific to Agent 3
    # ------------------------------------------------------------------

    def _query_cluster_neighbourhood(
        self, mgr: Neo4jConnectionManager, account_id: str
    ) -> list[dict]:
        """Bounded 2-hop neighbourhood for cluster detection."""
        limit = min(self._config.transfer_query_limit, 200)
        cypher = _CLUSTER_NEIGHBOURHOOD.format(limit=limit)
        with mgr.session() as session:
            result = session.run(cypher, account_id=account_id)
            return result.data()

    def _query_layering_paths(
        self, mgr: Neo4jConnectionManager, account_id: str
    ) -> list[dict]:
        """
        Bounded multi-hop paths from the sender account.

        Neo4j 5 / GQL 1.0 does not support parameterised hop ranges in
        variable-length patterns. Integer literals are interpolated from
        validated Agent3Config values — safe (never user-supplied text).
        """
        min_hops = self._config.min_layering_hops
        max_hops = self._config.max_layering_hops
        limit = self._config.layering_path_limit

        cypher = _LAYERING_MULTI_HOP.format(
            min_hops=min_hops,
            max_hops=max_hops,
            limit=limit,
        )
        with mgr.session() as session:
            result = session.run(cypher, sender_id=account_id)
            return result.data()

    # ------------------------------------------------------------------
    # Error output factory
    # ------------------------------------------------------------------

    def _make_error_output(
        self,
        error: str,
        status: Agent3Status,
        transaction: Optional[CanonicalTransaction] = None,
        agent1_output: Any = None,
        agent2_output: Any = None,
        graph_ingestion_performed: bool = False,
    ) -> Agent3Output:
        return Agent3Output(
            transaction_id=transaction.raw_record_id if transaction else None,
            source_dataset=(
                str(transaction.source_dataset)
                if (transaction and transaction.source_dataset)
                else None
            ),
            sender_account_id=(
                transaction.sender.account_id
                if (transaction and transaction.sender)
                else None
            ),
            receiver_account_id=(
                transaction.receiver.account_id
                if (transaction and transaction.receiver)
                else None
            ),
            status=status,
            errors=[error],
            detectors_run=[],
            detectors_skipped=_all_detector_names(),
            graph_ingestion_performed=graph_ingestion_performed,
            findings=[],
            finding_count=0,
            agent1_output_ref=_get_output_ref(agent1_output),
            agent2_output_ref=_get_output_ref(agent2_output),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_detector_names() -> list[str]:
    return ["LAYERING", "STRUCTURING", "FAN_IN", "FAN_OUT", "MULE_LIKE",
            "RAPID_FORWARDING", "SUSPICIOUS_CLUSTER"]


def _get_output_ref(output: Any) -> Optional[str]:
    """Extract a run_id reference from a prior agent output, if available."""
    if output is None:
        return None
    # Agent1Output has no run_id, use transaction_id as correlation
    for attr in ("agent1_run_id", "agent2_run_id", "transaction_id"):
        val = getattr(output, attr, None)
        if val:
            return str(val)
    return None
