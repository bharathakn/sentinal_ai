"""Phase 12 — LangGraph investigation pipeline: order, handoff rules, failure paths."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.agents.agent1.output_schema import Agent1Output, AgentStatus
from src.agents.agent3.output_schema import Agent3Output, Agent3Status
from src.agents.investigation import Investigator
from src.agents.pipeline_graph import (
    NodeName, NodeOutcome, PipelineStatus, build_investigation_graph,
)
from src.agents.sentinel_pipeline import new_case_state
from src.data.synthetic_india_generator import SyntheticIndiaDatasetGenerator
from src.evidence.data_store import IndiaSyntheticStore, set_store
from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

SMALL = dict(seed=11, num_transactions=900, num_customers=150, num_accounts=190)


@pytest.fixture(scope="module")
def small_data(tmp_path_factory):
    out = tmp_path_factory.mktemp("india_small_graph")
    data = SyntheticIndiaDatasetGenerator(**SMALL).generate_all()
    for name, df in data.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return out, data


@pytest.fixture()
def store(small_data):
    set_store(IndiaSyntheticStore(small_data[0]))
    yield
    set_store(None)


@pytest.fixture()
def tx(small_data, store):
    d = small_data[1]
    row = {**d["transactions_features"].iloc[20].to_dict(), **d["transactions_targets"].iloc[20].to_dict()}
    return IndiaSyntheticAdapter.from_row(row)


class FakeA1:
    def __init__(self):
        self.seen = []

    def score(self, tx):
        self.seen.append(tx.metadata.risk_label)
        return Agent1Output(scored_at_utc=datetime.now(timezone.utc), status=AgentStatus.COMPLETE,
                            anomaly_score=0.2, isolation_score=0.4, combined_confidence=0.2)


class FakeA3:
    def __call__(self, state):
        return {**state, "agent3_output": Agent3Output(status=Agent3Status.COMPLETE)}


class Raising:
    def __init__(self, exc=RuntimeError("secret-token=abc123 leaked")):
        self.exc = exc

    def __call__(self, state):
        raise self.exc


def _trace(state):
    return [(r.node, r.outcome) for r in state["pipeline_trace"]]


def _node(state, name):
    return next(r for r in state["pipeline_trace"] if r.node == name)


class TestHappyPath:
    def test_nodes_run_in_order_and_case_completes(self, tx):
        a1 = FakeA1()
        st = Investigator(agent1=a1, agent3=FakeA3()).investigate(tx, case_id="CASE-G")
        assert [n for n, _ in _trace(st)] == [
            NodeName.ANOMALY_DETECTOR, NodeName.EVIDENCE_GATHERER, NodeName.NETWORK_ANALYSER,
            NodeName.RISK_ASSESSOR, NodeName.EXPLANATION_GENERATOR, NodeName.OUTPUT_VALIDATOR]
        assert all(o == NodeOutcome.OK for _, o in _trace(st))
        assert st["pipeline_status"] == PipelineStatus.COMPLETE.value
        assert st["pipeline_version"] and st["case_completed_at_utc"] >= st["case_created_at_utc"]
        assert a1.seen == [None]  # label firewall still applied before Agent 1
        assert st["case_id"] == "CASE-G"
        assert st["validation_output"].status.value == "VALIDATED"
        assert st["agent5_output"].validation_status == "VALIDATED"
        assert _node(st, NodeName.OUTPUT_VALIDATOR).output_status == "VALIDATED"
        assert _node(st, NodeName.RISK_ASSESSOR).output_status == st["agent4_output"].status.value

    def test_no_report_mode_stops_after_risk_assessor(self, tx):
        st = Investigator(agent1=FakeA1(), agent3=FakeA3(), generate_report=False).investigate(tx)
        assert [n for n, _ in _trace(st)][-1] == NodeName.RISK_ASSESSOR
        assert "agent5_output" not in st and "validation_output" not in st
        assert st["pipeline_status"] == PipelineStatus.COMPLETE.value

    def test_graph_instance_reused_across_cases(self, tx):
        inv = Investigator(agent1=FakeA1(), agent3=FakeA3(), generate_report=False)
        s1, s2 = inv.investigate(tx), inv.investigate(tx)
        assert s1["case_id"] != s2["case_id"]
        assert len(s1["pipeline_trace"]) == len(s2["pipeline_trace"]) == 4  # traces do not accumulate


class TestHandoffRules:
    def test_node_cannot_overwrite_fields_it_does_not_own(self, tx):
        class Meddling:
            def __call__(self, state):
                return {**state, "transaction": None, "agent1_output": None, "case_id": "HIJACK",
                        "agent3_output": Agent3Output(status=Agent3Status.COMPLETE)}

        st = Investigator(agent1=FakeA1(), agent3=Meddling(), generate_report=False).investigate(tx, case_id="C-1")
        assert st["case_id"] == "C-1"
        assert st["transaction"] is not None and st["agent1_output"] is not None
        assert _node(st, NodeName.NETWORK_ANALYSER).outcome == NodeOutcome.OK

    def test_wrong_output_type_is_rejected(self, tx):
        class WrongType:
            def __call__(self, state):
                return {**state, "agent3_output": {"status": "COMPLETE"}}

        st = Investigator(agent1=FakeA1(), agent3=WrongType(), generate_report=False).investigate(tx)
        rec = _node(st, NodeName.NETWORK_ANALYSER)
        assert rec.outcome == NodeOutcome.ERROR and rec.error.startswith("HandoffError: agent3_output is dict")
        assert "agent3_output" not in st
        assert st["pipeline_status"] == PipelineStatus.DEGRADED.value

    def test_missing_output_is_a_handoff_error(self, tx):
        st = Investigator(agent1=FakeA1(), agent3=lambda s: dict(s), generate_report=False).investigate(tx)
        assert _node(st, NodeName.NETWORK_ANALYSER).error == "HandoffError: agent3_output not produced"

    def test_report_requires_validator(self):
        with pytest.raises(ValueError, match="bypass validation"):
            build_investigation_graph(agent1=FakeA1(), agent3=FakeA3(), agent4=lambda s: s, agent5=lambda s: s)

    def test_report_path_has_no_edge_around_validator(self):
        g = Investigator(agent1=FakeA1(), agent3=FakeA3()).graph.get_graph()
        out = {(e.source, e.target) for e in g.edges}
        from_generator = {t for s, t in out if s == NodeName.EXPLANATION_GENERATOR.value}
        assert from_generator == {NodeName.OUTPUT_VALIDATOR.value}


class TestFailurePaths:
    def test_agent_exception_degrades_and_continues(self, tx):
        st = Investigator(agent1=FakeA1(), agent3=Raising()).investigate(tx)
        rec = _node(st, NodeName.NETWORK_ANALYSER)
        assert rec.outcome == NodeOutcome.ERROR and rec.error == "RuntimeError"
        assert "secret" not in rec.model_dump_json()  # exception messages never reach the audit trail
        assert "agent3_output" not in st
        a4 = st["agent4_output"]
        assert a4.status.value == "PARTIAL"
        assert "NETWORK_RISK" in {s.value for s in a4.unavailable_signals}
        # the report is written but cannot be validated: an upstream output is missing
        assert st["validation_output"].status.value == "NEEDS_HUMAN_REVIEW"
        assert st["agent5_output"].validation_status == "NEEDS_HUMAN_REVIEW"
        assert st["pipeline_status"] == PipelineStatus.DEGRADED.value

    def test_agent1_exception_still_reaches_risk_assessor(self, tx):
        class BadA1:
            def score(self, tx):
                raise ValueError("boom")

        st = Investigator(agent1=BadA1(), agent3=FakeA3(), generate_report=False).investigate(tx)
        assert _node(st, NodeName.ANOMALY_DETECTOR).outcome == NodeOutcome.ERROR
        assert "ANOMALY" in {s.value for s in st["agent4_output"].unavailable_signals}

    @pytest.mark.parametrize("a4_status", ["FAILED", "VALIDATION_ERROR"])
    def test_no_risk_score_halts_before_report(self, tx, a4_status):
        from src.agents.agent4 import RiskAssessorAgent

        real = RiskAssessorAgent()

        def failing_a4(state):
            out = real(state)["agent4_output"].model_copy(update={"status": a4_status, "risk_score": None})
            return {**state, "agent4_output": out}

        st = Investigator(agent1=FakeA1(), agent3=FakeA3(), agent4=failing_a4).investigate(tx)
        nodes = [n for n, _ in _trace(st)]
        assert nodes[-1] == NodeName.HALT_FOR_REVIEW
        assert NodeName.EXPLANATION_GENERATOR not in nodes
        assert "agent5_output" not in st and "validation_output" not in st
        assert st["pipeline_status"] == PipelineStatus.HALTED.value
        assert a4_status in st["halt_reason"] and "human review" in st["halt_reason"]

    def test_risk_assessor_exception_halts(self, tx):
        st = Investigator(agent1=FakeA1(), agent3=FakeA3(), agent4=Raising()).investigate(tx)
        assert st["pipeline_status"] == PipelineStatus.HALTED.value
        assert "produced no output" in st["halt_reason"]

    def test_report_generator_exception_is_validated_as_missing_report(self, tx):
        st = Investigator(agent1=FakeA1(), agent3=FakeA3(), agent5=Raising()).investigate(tx)
        assert "agent5_output" not in st
        v = st["validation_output"]
        assert v.status.value == "NEEDS_HUMAN_REVIEW"
        assert st["pipeline_status"] == PipelineStatus.DEGRADED.value

    def test_validator_exception_leaves_report_not_validated(self, tx):
        st = Investigator(agent1=FakeA1(), agent3=FakeA3(), validation_stage=Raising()).investigate(tx)
        assert st["agent5_output"].validation_status == "NOT_VALIDATED"
        assert "validation_output" not in st
        assert _node(st, NodeName.OUTPUT_VALIDATOR).outcome == NodeOutcome.ERROR
        assert st["pipeline_status"] == PipelineStatus.DEGRADED.value


def test_direct_graph_invoke_matches_investigator(tx):
    """The compiled graph can be driven directly from new_case_state (e.g. by the Phase 13 API)."""
    from src.agents.agent4 import RiskAssessorAgent

    g = build_investigation_graph(agent1=FakeA1(), agent3=FakeA3(), agent4=RiskAssessorAgent())
    st = g.invoke(new_case_state(tx, case_id="CASE-D"))
    assert st["case_id"] == "CASE-D" and st["pipeline_status"] == PipelineStatus.COMPLETE.value
