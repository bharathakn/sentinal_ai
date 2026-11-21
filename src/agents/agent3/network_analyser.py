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
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ...schemas.canonical_transaction import CanonicalTransaction
from ...graph.connection import (
    Neo4jConnectionManager,
    Neo4jConfigError,
    Neo4jAuthError,
    Neo4jConnectivityError,
)
from ...graph.loader import TransactionGraphLoader
from ...graph.mapping import make_tx_graph_id
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
    NetworkPatternType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# v2 temporal queries (Phase 9.5)
# ---------------------------------------------------------------------------
# Timestamps are stored as uniform UTC ISO-8601 strings, so window bounds are
# compared lexicographically. Hop-range integers are interpolated from
# validated Agent3Config values (never user text); all other values are
# query parameters.

_TRANSFER_FIELDS = """
    r.tx_graph_id   AS tx_graph_id,
    r.raw_record_id AS raw_record_id,
    r.amount        AS amount,
    r.amount_str    AS amount_str,
    r.currency      AS currency,
    r.timestamp_utc AS timestamp_utc,
    r.channel       AS channel
"""

_WINDOW_OUT = """
MATCH (a:Account {account_id: $account_id})-[r:TRANSFERRED_TO]->(b:Account)
WHERE r.timestamp_utc >= $from_ts AND r.timestamp_utc <= $to_ts
RETURN a.account_id AS account_id, b.account_id AS counterpart_id, """ + _TRANSFER_FIELDS + """
ORDER BY r.timestamp_utc
LIMIT $limit
"""

_WINDOW_IN = """
MATCH (b:Account)-[r:TRANSFERRED_TO]->(a:Account {account_id: $account_id})
WHERE r.timestamp_utc >= $from_ts AND r.timestamp_utc <= $to_ts
RETURN a.account_id AS account_id, b.account_id AS counterpart_id, """ + _TRANSFER_FIELDS + """
ORDER BY r.timestamp_utc
LIMIT $limit
"""

# Doubled braces: this fragment is embedded in templates passed to str.format().
_REL_MAP = """{{tx_graph_id: c.tx_graph_id, amount: c.amount, amount_str: c.amount_str,
               currency: c.currency, timestamp_utc: c.timestamp_utc, channel: c.channel}}"""

_CHAIN_OK = """
all(i IN range(1, size(chain) - 1) WHERE
    chain[i].timestamp_utc > chain[i - 1].timestamp_utc
    AND chain[i].amount >= $retention * chain[i - 1].amount
    AND duration.inSeconds(datetime(chain[i - 1].timestamp_utc),
                           datetime(chain[i].timestamp_utc)).seconds <= $max_gap_s)
"""

_LAYERING_FORWARD = """
MATCH (s:Account {{account_id: $sender_id}})-[r0:TRANSFERRED_TO {{tx_graph_id: $tx_graph_id}}]->(r:Account)
MATCH p = (r)-[rels:TRANSFERRED_TO*1..{k}]->(:Account)
WHERE all(x IN rels WHERE x.timestamp_utc > r0.timestamp_utc AND x.timestamp_utc <= $to_ts)
WITH p, rels, [r0] + rels AS chain
WHERE """ + _CHAIN_OK + """
RETURN [n IN nodes(p) | n.account_id] AS node_ids,
       [c IN chain | """ + _REL_MAP + """] AS transfers
ORDER BY size(rels) DESC
LIMIT 25
"""

_LAYERING_BACKWARD = """
MATCH (s:Account {{account_id: $sender_id}})-[r0:TRANSFERRED_TO {{tx_graph_id: $tx_graph_id}}]->(:Account)
MATCH p = (:Account)-[rels:TRANSFERRED_TO*1..{k}]->(s)
WHERE all(x IN rels WHERE x.timestamp_utc < r0.timestamp_utc AND x.timestamp_utc >= $from_ts)
WITH p, rels, rels + [r0] AS chain
WHERE """ + _CHAIN_OK + """
RETURN [n IN nodes(p) | n.account_id] AS node_ids,
       [c IN rels | """ + _REL_MAP + """] AS transfers
ORDER BY size(rels) DESC
LIMIT 25
"""

_CYCLES = """
MATCH p = (a:Account {{account_id: $account_id}})-[rels:TRANSFERRED_TO*{min_len}..{max_len}]->(a)
WHERE all(x IN rels WHERE x.timestamp_utc >= $from_ts AND x.timestamp_utc <= $to_ts)
// Time ordering is checked by the detector over every rotation of the cycle:
// a ring m1→m2→…→m1 is only ordered when read from the account that started it.
RETURN [n IN nodes(p) | n.account_id] AS node_ids,
       [c IN rels | """ + _REL_MAP + """] AS transfers
LIMIT 50
"""


_GRAPH_TRANSFER_COUNT = "MATCH ()-[r:TRANSFERRED_TO]->() RETURN count(r) AS transfers"


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _combine_chains(back: list[dict], fwd: list[dict], sender_id: str) -> list[dict]:
    """Join backward chains (ending at sender) with forward chains (starting with the subject transfer)."""
    backs = [{"node_ids": [sender_id], "transfers": []}] + [b for b in back if b.get("node_ids")]
    out = []
    for b in backs[:6]:
        for f in fwd[:6]:
            out.append({
                "node_ids": list(b["node_ids"]) + list(f["node_ids"]),
                "transfers": list(b["transfers"]) + list(f["transfers"]),
            })
    return out


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
        # Step 2b: Graph population check. An empty / unloaded graph must not
        # produce a COMPLETE "no patterns" result.
        # ------------------------------------------------------------------
        cfg = self._config
        graph_underpopulated = False
        try:
            cnt = self._run(mgr, _GRAPH_TRANSFER_COUNT)
            if cnt and cnt[0].get("transfers") is not None:
                total = int(cnt[0]["transfers"])
                if total < cfg.min_graph_transfers:
                    graph_underpopulated = True
                    warnings.append(
                        f"Graph holds only {total} transfer(s) (minimum {cfg.min_graph_transfers}); it appears "
                        "empty or not loaded. Absence of network patterns is not a clean result."
                    )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Graph size check failed: {type(exc).__name__}")

        # ------------------------------------------------------------------
        # Step 3: Analysis window around the investigated transaction (v2)
        # ------------------------------------------------------------------
        anchor = transaction.timestamp
        if anchor is None:
            warnings.append(
                "Transaction timestamp missing: temporal window cannot be anchored; "
                "layering skipped and all available history analysed."
            )
            from_ts, to_ts = "0000", "9999"
        else:
            from_ts = _iso_utc(anchor - timedelta(hours=cfg.lookback_hours))
            to_ts = _iso_utc(anchor + timedelta(hours=cfg.horizon_hours))

        limit = cfg.transfer_query_limit
        subjects = [sender_id] + ([receiver_id] if receiver_id != sender_id else [])
        rows: dict[str, dict[str, list[dict]]] = {}
        cycles: dict[str, list[dict]] = {}
        for acc in subjects:
            rows[acc] = {"in": [], "out": []}
            for direction, cypher in (("out", _WINDOW_OUT), ("in", _WINDOW_IN)):
                try:
                    rows[acc][direction] = self._run(mgr, cypher, account_id=acc,
                                                     from_ts=from_ts, to_ts=to_ts, limit=limit)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{direction} transfer query failed for {acc}: {type(exc).__name__}")
                    detectors_skipped.extend(
                        ["STRUCTURING", "FAN_OUT", "RAPID_FORWARDING", "MULE_LIKE"] if direction == "out"
                        else ["FAN_IN", "RAPID_FORWARDING", "MULE_LIKE"])
                    rows[acc][direction] = []
            try:
                cycles[acc] = self._run(
                    mgr,
                    _CYCLES.format(min_len=cfg.cluster_min_edges, max_len=cfg.cluster_max_cycle_length),
                    account_id=acc, from_ts=from_ts, to_ts=to_ts)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Cycle query failed for {acc}: {type(exc).__name__}")
                detectors_skipped.append("SUSPICIOUS_CLUSTER")
                cycles[acc] = []
        detectors_run.append("graph_fetch_window")

        paths: list[dict] = []
        if anchor is not None:
            try:
                k = max(cfg.max_layering_hops - 1, 1)
                params = dict(sender_id=sender_id, tx_graph_id=make_tx_graph_id(transaction),
                              from_ts=from_ts, to_ts=to_ts,
                              retention=cfg.layering_min_amount_retention,
                              max_gap_s=int(cfg.layering_hop_max_gap_hours * 3600))
                fwd = self._run(mgr, _LAYERING_FORWARD.format(k=k), **params)
                back = self._run(mgr, _LAYERING_BACKWARD.format(k=k), **params)
                paths = _combine_chains(back, fwd, sender_id)
                detectors_run.append("graph_fetch_paths")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Layering path query failed: {type(exc).__name__}")
                detectors_skipped.append("LAYERING")
        else:
            detectors_skipped.append("LAYERING")

        # ------------------------------------------------------------------
        # Step 4: Run v2 detectors for the sender and the receiver
        # ------------------------------------------------------------------
        def run(name: str, fn, *args) -> None:
            if name in detectors_skipped:
                return
            try:
                findings.extend(fn(*args, cfg))
                detectors_run.append(name)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{name} detector error: {type(exc).__name__}")
                detectors_skipped.append(name)

        run("LAYERING", detect_layering, paths, sender_id)
        for acc in subjects:
            r_in, r_out = rows[acc]["in"], rows[acc]["out"]
            run("STRUCTURING", detect_structuring, r_out, acc)
            run("FAN_IN", detect_fan_in, r_in, acc)
            run("FAN_OUT", detect_fan_out, r_out, acc)
            run("MULE_LIKE", detect_mule_like, r_in, r_out, acc)
            run("RAPID_FORWARDING", detect_rapid_forwarding, r_in, r_out, acc)
            run("SUSPICIOUS_CLUSTER", detect_suspicious_cluster, cycles[acc], acc)

        # A cycle through both sender and receiver is reported once.
        deduped, seen_cycles = [], set()
        for f in findings:
            if f.pattern_type == NetworkPatternType.SUSPICIOUS_CLUSTER:
                key = frozenset([f.subject_account_id, *f.related_account_ids])
                if key in seen_cycles:
                    continue
                seen_cycles.add(key)
            deduped.append(f)
        findings = deduped

        # ------------------------------------------------------------------
        # Step 5: Assemble output
        # ------------------------------------------------------------------
        status = (
            Agent3Status.PARTIAL
            if detectors_skipped or graph_underpopulated
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

    @staticmethod
    def _run(mgr: Neo4jConnectionManager, cypher: str, **params) -> list[dict]:
        with mgr.session() as session:
            return session.run(cypher, **params).data()

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
