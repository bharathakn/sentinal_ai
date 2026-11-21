"""
Sentinel AI — LangGraph investigation pipeline (Phase 12).

    START → anomaly_detector → evidence_gatherer → network_analyser → risk_assessor
          ├─(no risk score)──────────────────────────────→ halt_for_review ─┐
          ├─(report disabled)──────────────────────────────────────────────┤
          └─→ explanation_generator → output_validator ────────────────────┴→ finalise → END

Handoff rules enforced by every node wrapper
--------------------------------------------
* A node receives a copy of the state and may write **only the fields it
  owns** (``NODE_OUTPUTS``). Anything else it returns is discarded, so no
  agent can change another agent's output or the transaction.
* Each owned field is type-checked against the agent's output schema before
  it enters the state. A wrong type is a handoff error and is not stored.
* An unexpected exception does not stop the graph. The node is recorded as
  ``ERROR`` (exception type only, no message, so nothing sensitive leaks into
  the audit trail), and downstream agents treat the missing output as an
  unavailable signal, as they already do.
* Every node appends one :class:`NodeRecord` to ``pipeline_trace``.

Failure behaviour
-----------------
* ``risk_assessor`` produced no risk score (output missing, ``FAILED`` or
  ``VALIDATION_ERROR``) → no report is written. The case is ``HALTED`` and
  Agent 4's fail-safe ``HUMAN_REVIEW`` decision (if any) stands.
* A report that did not pass through the validator keeps
  ``validation_status = NOT_VALIDATED``. Validation can never be skipped
  on the report path: the only edge out of ``explanation_generator`` leads to
  ``output_validator``.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict

from .sentinel_pipeline import SentinelState

PIPELINE_VERSION = "1.0.0"


class NodeName(str, Enum):
    ANOMALY_DETECTOR = "anomaly_detector"
    EVIDENCE_GATHERER = "evidence_gatherer"
    NETWORK_ANALYSER = "network_analyser"
    RISK_ASSESSOR = "risk_assessor"
    EXPLANATION_GENERATOR = "explanation_generator"
    OUTPUT_VALIDATOR = "output_validator"
    HALT_FOR_REVIEW = "halt_for_review"
    FINALISE = "finalise"


class NodeOutcome(str, Enum):
    OK = "OK"
    ERROR = "ERROR"


class PipelineStatus(str, Enum):
    COMPLETE = "COMPLETE"   # every node ran without an exception or handoff error
    DEGRADED = "DEGRADED"   # at least one node failed; later agents worked with less evidence
    HALTED = "HALTED"       # no risk score; no report; human review required


class NodeRecord(BaseModel):
    """Audit record of one node execution."""

    model_config = ConfigDict(frozen=True)

    node: NodeName
    outcome: NodeOutcome
    output_status: Optional[str] = None  # the agent's own status (COMPLETE, PARTIAL, …)
    started_at_utc: datetime
    duration_ms: float
    error: Optional[str] = None          # exception type / handoff problem; never a message


def _output_types() -> dict[str, type]:
    from .agent1.output_schema import Agent1Output
    from .agent2.output_schema import Agent2Output
    from .agent3.output_schema import Agent3Output
    from .agent4.output_schema import Agent4Output
    from .agent5.report_schema import Agent5Output
    from .validator.schema import ValidationOutput

    return {
        "agent1_output": Agent1Output, "agent2_output": Agent2Output, "agent3_output": Agent3Output,
        "agent4_output": Agent4Output, "agent5_output": Agent5Output, "validation_output": ValidationOutput,
        "rejected_reports": list,
    }


#: Fields each node may write. The first is required and gives the output status.
NODE_OUTPUTS: dict[NodeName, tuple[str, ...]] = {
    NodeName.ANOMALY_DETECTOR: ("agent1_output",),
    NodeName.EVIDENCE_GATHERER: ("agent2_output",),
    NodeName.NETWORK_ANALYSER: ("agent3_output",),
    NodeName.RISK_ASSESSOR: ("agent4_output",),
    NodeName.EXPLANATION_GENERATOR: ("agent5_output",),
    # The validator may replace the presented report with a validated template one.
    NodeName.OUTPUT_VALIDATOR: ("validation_output", "agent5_output", "rejected_reports"),
}

_NO_DECISION_STATUSES = {"FAILED", "VALIDATION_ERROR"}


def _status_of(obj: Any) -> Optional[str]:
    s = getattr(obj, "status", None)
    return getattr(s, "value", s) if s is not None else None


def guarded_node(name: NodeName, fn: Callable[[dict], dict]) -> Callable[[SentinelState], dict]:
    """Wrap a state-in / state-out callable as a LangGraph node that enforces
    the handoff rules (owned fields only, typed outputs, errors recorded)."""
    owned = NODE_OUTPUTS[name]
    types = _output_types()

    def node(state: SentinelState) -> dict:
        started, t0 = datetime.now(timezone.utc), time.perf_counter()
        update: dict = {}
        error: Optional[str] = None
        try:
            result = fn(dict(state)) or {}
            for key in owned:
                if key not in result:
                    continue
                if not isinstance(result[key], types[key]):
                    raise _HandoffError(f"HandoffError: {key} is {type(result[key]).__name__}, "
                                        f"expected {types[key].__name__}")
                update[key] = result[key]
            if owned[0] not in update:
                raise _HandoffError(f"HandoffError: {owned[0]} not produced")
        except _HandoffError as exc:
            update, error = {}, str(exc)
        except Exception as exc:  # noqa: BLE001 — recorded; the graph continues
            update, error = {}, type(exc).__name__
        record = NodeRecord(
            node=name, outcome=NodeOutcome.ERROR if error else NodeOutcome.OK,
            output_status=_status_of(update.get(owned[0])), started_at_utc=started,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2), error=error,
        )
        update["pipeline_trace"] = [record]
        return update

    node.__name__ = name.value
    return node


class _HandoffError(Exception):
    pass


def _halt(state: SentinelState) -> dict:
    a4 = state.get("agent4_output")
    reason = ("Risk Assessor produced no output" if a4 is None
              else f"Risk Assessor status {_status_of(a4)}: no risk score")
    return {
        "halt_reason": reason + "; report not generated; case requires human review.",
        "pipeline_trace": [NodeRecord(node=NodeName.HALT_FOR_REVIEW, outcome=NodeOutcome.OK,
                                      started_at_utc=datetime.now(timezone.utc), duration_ms=0.0)],
    }


def _finalise(state: SentinelState) -> dict:
    trace = state.get("pipeline_trace") or []
    if state.get("halt_reason"):
        status = PipelineStatus.HALTED
    elif any(r.outcome == NodeOutcome.ERROR for r in trace):
        status = PipelineStatus.DEGRADED
    else:
        status = PipelineStatus.COMPLETE
    return {"pipeline_status": status.value, "pipeline_version": PIPELINE_VERSION,
            "case_completed_at_utc": datetime.now(timezone.utc)}


def build_investigation_graph(
    agent1: Any,
    agent3: Any,
    agent4: Any,
    agent5: Any = None,
    validation_stage: Any = None,
    evidence_gatherer: Optional[Callable] = None,
):
    """Compile the investigation graph.

    ``agent1`` needs ``score(tx)``; ``evidence_gatherer(tx, agent1_output)``
    defaults to Agent 2's ``gather_evidence``; ``agent3`` / ``agent4`` /
    ``agent5`` / ``validation_stage`` are state-in / state-out callables.
    ``agent5=None`` builds the graph without the report path (bulk evaluation).
    """
    if (agent5 is None) != (validation_stage is None):
        raise ValueError("agent5 and validation_stage must be given together: "
                         "a report must never bypass validation.")
    if evidence_gatherer is None:
        from .agent2.evidence_gatherer import gather_evidence as evidence_gatherer

    g = StateGraph(SentinelState)
    g.add_node(NodeName.ANOMALY_DETECTOR.value, guarded_node(
        NodeName.ANOMALY_DETECTOR, lambda s: {"agent1_output": agent1.score(s["transaction"])}))
    g.add_node(NodeName.EVIDENCE_GATHERER.value, guarded_node(
        NodeName.EVIDENCE_GATHERER,
        lambda s: {"agent2_output": evidence_gatherer(s["transaction"], s.get("agent1_output"))}))
    g.add_node(NodeName.NETWORK_ANALYSER.value, guarded_node(NodeName.NETWORK_ANALYSER, agent3))
    g.add_node(NodeName.RISK_ASSESSOR.value, guarded_node(NodeName.RISK_ASSESSOR, agent4))
    g.add_node(NodeName.HALT_FOR_REVIEW.value, _halt)
    g.add_node(NodeName.FINALISE.value, _finalise)

    g.add_edge(START, NodeName.ANOMALY_DETECTOR.value)
    g.add_edge(NodeName.ANOMALY_DETECTOR.value, NodeName.EVIDENCE_GATHERER.value)
    g.add_edge(NodeName.EVIDENCE_GATHERER.value, NodeName.NETWORK_ANALYSER.value)
    g.add_edge(NodeName.NETWORK_ANALYSER.value, NodeName.RISK_ASSESSOR.value)

    next_after_risk = NodeName.FINALISE.value
    if agent5 is not None:
        g.add_node(NodeName.EXPLANATION_GENERATOR.value, guarded_node(NodeName.EXPLANATION_GENERATOR, agent5))
        g.add_node(NodeName.OUTPUT_VALIDATOR.value, guarded_node(NodeName.OUTPUT_VALIDATOR, validation_stage))
        g.add_edge(NodeName.EXPLANATION_GENERATOR.value, NodeName.OUTPUT_VALIDATOR.value)
        g.add_edge(NodeName.OUTPUT_VALIDATOR.value, NodeName.FINALISE.value)
        next_after_risk = NodeName.EXPLANATION_GENERATOR.value

    def route_after_risk(state: SentinelState) -> str:
        a4 = state.get("agent4_output")
        if a4 is None or _status_of(a4) in _NO_DECISION_STATUSES:
            return NodeName.HALT_FOR_REVIEW.value
        return next_after_risk

    g.add_conditional_edges(NodeName.RISK_ASSESSOR.value, route_after_risk,
                            [NodeName.HALT_FOR_REVIEW.value, next_after_risk])
    g.add_edge(NodeName.HALT_FOR_REVIEW.value, NodeName.FINALISE.value)
    g.add_edge(NodeName.FINALISE.value, END)
    return g.compile()


__all__ = ["build_investigation_graph", "guarded_node", "NodeName", "NodeOutcome", "NodeRecord",
           "PipelineStatus", "PIPELINE_VERSION", "NODE_OUTPUTS"]
