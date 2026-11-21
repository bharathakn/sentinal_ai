"""
Sentinel AI — Investigation Pipeline State.

Defines the shared state that flows through the agent pipeline.
Implemented as a TypedDict for direct LangGraph compatibility —
when LangGraph is installed, use this as the State annotation.

Architecture
------------
Agent 1 (Anomaly Detector)  →  writes agent1_output
Agent 2 (Evidence Gatherer) →  reads agent1_output, writes agent2_output
Agent 3 (Network Analyser)  →  reads agent2_output, writes agent3_output
Agent 4 (Risk Assessor)     →  reads agent1/2/3 outputs, writes agent4_output
Agent 5 (Explanation Gen.)  →  reads all outputs, writes agent5_output (draft report)
Output Validator            →  writes validation_output (may replace agent5_output
                               with a validated template report; rejected_reports)

Orchestration (Phase 12): `src/agents/pipeline_graph.build_investigation_graph`
compiles a LangGraph `StateGraph(SentinelState)`; `Investigator` runs it.

Rules
-----
* Each agent reads from the established state fields and writes only its own
  output field. No agent modifies another agent's output.
* The `transaction` field is immutable once set by the graph entry point.
* Optional agent outputs are None until the corresponding agent has run.
* The graph enforces these rules: each node may write only the fields it
  owns, typed, and appends one record to `pipeline_trace` (a LangGraph
  append reducer).
"""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, Any, Optional
from uuid import uuid4

from typing_extensions import TypedDict

from ..schemas.canonical_transaction import CanonicalTransaction
from .agent1.output_schema import Agent1Output
from .agent2.output_schema import Agent2Output
from .agent3.output_schema import Agent3Output
from .agent4.output_schema import Agent4Output
from .agent5.report_schema import Agent5Output


class SentinelState(TypedDict, total=False):
    """Shared investigation state flowing through the Sentinel AI pipeline.

    Fields
    ------
    case_id       : Investigation case identifier (set by new_case_state).
    case_created_at_utc : When the case was opened (UTC).
    transaction   : The canonical transaction being investigated, with
                    ground-truth label fields removed. Required.
    agent1_output : Output from Agent 1 (Anomaly Detector). Set after Agent 1.
    agent2_output : Output from Agent 2 (Evidence Gatherer). Set after Agent 2.
    agent3_output : Output from Agent 3 (Network Analyser). Set after Agent 3.
    agent4_output : Output from Agent 4 (Risk Assessor). Set after Agent 4.
    agent5_output : Output from Agent 5 (Explanation Generator): report with
                    its evidence bundle; validation_status set by the validator.
    validation_output : Output Validator result for the presented report.
    rejected_reports  : Reports generated but not presented (failed
                        validation), kept with their validation for audit.
    pipeline_trace    : One NodeRecord per executed graph node (appended).
    halt_reason       : Set when the graph halted before the report (no risk score).
    pipeline_status   : COMPLETE / DEGRADED / HALTED (set by the final node).
    pipeline_version  : Version of the orchestration graph.
    case_completed_at_utc : When the graph finished.
    """

    case_id: str
    case_created_at_utc: datetime
    transaction: CanonicalTransaction
    agent1_output: Optional[Agent1Output]
    agent2_output: Optional[Agent2Output]
    agent3_output: Optional[Agent3Output]
    agent4_output: Optional[Agent4Output]
    agent5_output: Optional[Agent5Output]
    validation_output: Optional[Any]   # validator.ValidationOutput (typed loosely: import order)
    rejected_reports: list[Any]
    pipeline_trace: Annotated[list[Any], operator.add]   # pipeline_graph.NodeRecord
    halt_reason: Optional[str]
    pipeline_status: str
    pipeline_version: str
    case_completed_at_utc: datetime


# ---------------------------------------------------------------------------
# Case entry point + label firewall (Phase 9.5)
# ---------------------------------------------------------------------------

GROUND_TRUTH_FIELDS = ("is_fraud", "metadata.risk_label", "metadata.scenario_id")
"""Dataset ground-truth labels. Evaluation code may read them; agents may not.

`metadata.is_flagged_fraud` and `metadata.alert_id` are NOT ground truth: they
describe the monitoring alert that opened the case and are kept.
"""


def strip_ground_truth(transaction: CanonicalTransaction) -> CanonicalTransaction:
    """Return a copy of the transaction with ground-truth label fields cleared."""
    update: dict = {"is_fraud": None}
    if transaction.metadata is not None:
        update["metadata"] = transaction.metadata.model_copy(
            update={"risk_label": None, "scenario_id": None}
        )
    return transaction.model_copy(update=update)


def new_case_id() -> str:
    return f"CASE-{uuid4().hex[:12].upper()}"


def new_case_state(
    transaction: CanonicalTransaction,
    case_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> SentinelState:
    """Create the initial pipeline state for an investigation.

    This is the ONLY supported entry point into the agent pipeline: it assigns
    the case identity and applies the label firewall, so no agent (and no LLM
    prompt built from agent outputs) can see dataset ground truth.
    """
    return SentinelState(
        case_id=case_id or new_case_id(),
        case_created_at_utc=created_at or datetime.now(timezone.utc),
        transaction=strip_ground_truth(transaction),
    )
