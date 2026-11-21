"""Phase 13 — investigation API, case service and case stores."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.agents.agent1.output_schema import Agent1Output, AgentStatus
from src.agents.agent3.output_schema import Agent3Output, Agent3Status
from src.api.app import create_app
from src.api.case_schema import (
    AlertInfo, AlertSource, AuditEvent, AuditEventType, CaseRecord, CaseStatus, CaseSummary, utcnow,
)
from src.api.case_store import JsonCaseStore, MongoCaseStore
from src.data.synthetic_india_generator import SyntheticIndiaDatasetGenerator
from src.evidence.data_store import IndiaSyntheticStore, set_store
from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

SMALL = dict(seed=11, num_transactions=900, num_customers=150, num_accounts=190)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def small_data(tmp_path_factory):
    out = tmp_path_factory.mktemp("india_small_api")
    data = SyntheticIndiaDatasetGenerator(**SMALL).generate_all()
    for name, df in data.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return out, data


@pytest.fixture()
def india(small_data):
    store = IndiaSyntheticStore(small_data[0])
    set_store(store)
    yield store
    set_store(None)


@pytest.fixture()
def tx_ids(small_data):
    return list(small_data[1]["transactions_features"]["transaction_id"].iloc[20:40])


class FakeA1:
    def __init__(self):
        self.seen_labels = []

    def score(self, tx):
        self.seen_labels.append((tx.is_fraud, tx.metadata.risk_label, tx.metadata.scenario_id))
        return Agent1Output(scored_at_utc=datetime.now(timezone.utc), status=AgentStatus.COMPLETE,
                            anomaly_score=0.2, isolation_score=0.4, combined_confidence=0.2)


class FakeA3:
    def __call__(self, state):
        return {**state, "agent3_output": Agent3Output(status=Agent3Status.COMPLETE)}


def make_factory(a1=None, **kw):
    from src.agents.investigation import Investigator

    return lambda: Investigator(agent1=a1 or FakeA1(), agent3=FakeA3(), **kw)


@pytest.fixture()
def store(tmp_path):
    return JsonCaseStore(tmp_path / "cases")


def client_for(store, india, factory=None, **kw):
    app = create_app(store=store, investigator_factory=factory or make_factory(),
                     feed_lookup=india.get_transaction, **kw)
    return TestClient(app)


def post_alert(c, wait=True, headers=None, **body):
    return c.post(f"/api/v1/alerts{'?wait=true' if wait else ''}", json=body, headers=headers or {})


def make_record(case_id, status, action=None, score=None, created=None, key=None):
    now = created or utcnow()
    return CaseRecord(
        case_id=case_id, transaction_key=key or f"X:{case_id}", status=status, created_at_utc=now, updated_at_utc=now,
        alert=AlertInfo(source=AlertSource.API, received_at_utc=now),
        transaction={"raw_record_id": f"T-{case_id}", "amount": "10.00", "currency": "INR"},
        summary=CaseSummary(recommended_action=action, risk_score=score,
                            priority_rank={"BLOCK": 5, "ESCALATE": 4, "HUMAN_REVIEW": 3, "MONITOR": 2,
                                           "CLEAR": 1}.get(action or "", 0)),
    )


# ---------------------------------------------------------------------------
# Ingestion and investigation
# ---------------------------------------------------------------------------

class TestIngestion:
    def test_health(self, store, india):
        with client_for(store, india) as c:
            h = c.get("/health").json()
        assert h["status"] == "ok" and h["case_store"] == "json" and h["case_store_ok"]
        assert "PROTOTYPE" in h["prototype_notice"]

    def test_feed_alert_is_investigated_and_stored(self, store, india, tx_ids):
        with client_for(store, india) as c:
            r = post_alert(c, transaction_id=tx_ids[0], alert_id="ALERT-1", source_system="tm-demo")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "AWAITING_REVIEW" and body["duplicate"] is False
            case = c.get(f"/api/v1/cases/{body['case_id']}").json()
        assert case["alert"] == {**case["alert"], "alert_id": "ALERT-1", "source": "SYNTHETIC_FEED",
                                 "source_system": "tm-demo"}
        inv = case["investigation"]
        assert inv["pipeline_status"] == "COMPLETE"
        assert [t["node"] for t in inv["pipeline_trace"]][-1] == "output_validator"
        s = case["summary"]
        assert s["recommended_action"] == inv["agent4_output"]["recommended_action"]
        assert s["risk_score"] == inv["agent4_output"]["risk_score"]
        assert s["validation_status"] == inv["validation_output"]["status"] == "VALIDATED"
        assert s["requires_human_review"] is False
        assert [e["event_type"] for e in case["audit_trail"]] == [
            "CASE_CREATED", "INVESTIGATION_STARTED", "INVESTIGATION_COMPLETED"]
        assert inv["agent5_output"]["case_id"] == case["case_id"]

    def test_labels_never_stored_or_seen(self, store, india, small_data):
        d = small_data[1]
        row = {**d["transactions_features"].iloc[25].to_dict(), **d["transactions_targets"].iloc[25].to_dict()}
        tx = IndiaSyntheticAdapter.from_row(row)
        payload = tx.model_dump(mode="json")
        payload["is_fraud"] = True
        payload["metadata"]["risk_label"] = "FRAUDULENT"
        payload["metadata"]["scenario_id"] = "SCENARIO_7_LAYERING_NETWORK"
        a1 = FakeA1()
        with client_for(store, india, factory=make_factory(a1)) as c:
            r = post_alert(c, transaction=payload)
            case = c.get(f"/api/v1/cases/{r.json()['case_id']}").json()
        assert case["alert"]["source"] == "API"
        assert case["transaction"]["is_fraud"] is None
        assert case["transaction"]["metadata"]["risk_label"] is None
        assert case["transaction"]["metadata"]["scenario_id"] is None
        assert a1.seen_labels == [(None, None, None)]

    def test_duplicate_alert_returns_existing_case(self, store, india, tx_ids):
        with client_for(store, india) as c:
            first = post_alert(c, transaction_id=tx_ids[1]).json()
            again = post_alert(c, transaction_id=tx_ids[1])
            assert again.status_code == 200
            assert again.json()["case_id"] == first["case_id"] and again.json()["duplicate"] is True
            assert c.get("/api/v1/cases").json()["total"] == 1

    @pytest.mark.parametrize("body", [{}, {"transaction_id": "T1", "transaction": {"x": 1}},
                                      {"transaction_id": "bad id!"}, {"transaction_id": "T1", "extra": 1}])
    def test_invalid_alerts_rejected(self, store, india, body):
        with client_for(store, india) as c:
            assert c.post("/api/v1/alerts", json=body).status_code == 422

    def test_unknown_feed_transaction(self, store, india):
        with client_for(store, india) as c:
            r = post_alert(c, transaction_id="TXN_IND_000000_999999")
        assert r.status_code == 404

    def test_ingest_api_key(self, store, india, tx_ids):
        with client_for(store, india, ingest_api_key="s3cret") as c:
            assert post_alert(c, transaction_id=tx_ids[2]).status_code == 401
            assert post_alert(c, transaction_id=tx_ids[2], headers={"X-API-Key": "wrong"}).status_code == 401
            assert post_alert(c, transaction_id=tx_ids[2], headers={"X-API-Key": "s3cret"}).status_code == 200
            assert c.get("/api/v1/cases").status_code == 200  # reads do not need the ingest key

    def test_queue_full(self, store, india, tx_ids, monkeypatch):
        monkeypatch.setenv("SENTINEL_MAX_PENDING_CASES", "0")
        with client_for(store, india) as c:
            r = post_alert(c, wait=False, transaction_id=tx_ids[3])
        assert r.status_code == 429 and r.headers["Retry-After"]

    def test_investigation_exception_recorded_without_message(self, store, india, tx_ids):
        class Boom:
            def investigate(self, tx, case_id=None):
                raise RuntimeError("password=hunter2 at mongodb+srv://host")

        with client_for(store, india, factory=lambda: Boom()) as c:
            body = post_alert(c, transaction_id=tx_ids[4]).json()
            assert body["status"] == "INVESTIGATION_FAILED"
            case = c.get(f"/api/v1/cases/{body['case_id']}")
            assert "hunter2" not in case.text and "mongodb" not in case.text
            assert case.json()["investigation_error"] == "RuntimeError"
            # a failed case does not block a new alert for the same transaction
            again = post_alert(c, transaction_id=tx_ids[4]).json()
            assert again["duplicate"] is False and again["case_id"] != body["case_id"]

    def test_investigator_start_failure_visible_in_health(self, store, india, tx_ids):
        def broken():
            raise FileNotFoundError("models/x")

        with client_for(store, india, factory=broken) as c:
            body = post_alert(c, transaction_id=tx_ids[5]).json()
            h = c.get("/health").json()
        assert body["status"] == "INVESTIGATION_FAILED"
        assert h["investigator_ready"] is False and h["investigator_error"] == "FileNotFoundError"

    def test_unfinished_cases_requeued_on_start(self, store, india, tx_ids):
        tx = IndiaSyntheticAdapter.from_row(india.get_transaction(tx_ids[6]))
        now = utcnow()
        store.create(CaseRecord(case_id="CASE-RESTART01", transaction_key="k", status=CaseStatus.INVESTIGATING,
                                created_at_utc=now, updated_at_utc=now,
                                alert=AlertInfo(source=AlertSource.API, received_at_utc=now),
                                transaction=tx.model_dump(mode="json")))
        with client_for(store, india) as c:
            for _ in range(100):
                case = c.get("/api/v1/cases/CASE-RESTART01").json()
                if case["status"] == "AWAITING_REVIEW":
                    break
                time.sleep(0.1)
        assert case["status"] == "AWAITING_REVIEW"
        assert [e["event_type"] for e in case["audit_trail"]][0] == "INVESTIGATION_REQUEUED"

    def test_halted_case_has_no_report(self, store, india, tx_ids):
        from src.agents.agent4 import RiskAssessorAgent

        real = RiskAssessorAgent()

        def failing_a4(state):
            from src.agents.agent4.output_schema import Agent4Status

            out = real(state)["agent4_output"].model_copy(update={"status": Agent4Status.FAILED, "risk_score": None})
            return {**state, "agent4_output": out}

        with client_for(store, india, factory=make_factory(agent4=failing_a4)) as c:
            body = post_alert(c, transaction_id=tx_ids[7]).json()
            assert body["status"] == "AWAITING_REVIEW"
            assert body["summary"]["pipeline_status"] == "HALTED"
            assert body["summary"]["requires_human_review"] is True
            r = c.get(f"/api/v1/cases/{body['case_id']}/report")
        assert r.status_code == 404 and "human review" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Reports, queue, decisions
# ---------------------------------------------------------------------------

class TestCaseViews:
    def test_report_json_and_markdown(self, store, india, tx_ids):
        with client_for(store, india) as c:
            cid = post_alert(c, transaction_id=tx_ids[8]).json()["case_id"]
            j = c.get(f"/api/v1/cases/{cid}/report").json()
            md = c.get(f"/api/v1/cases/{cid}/report?format=markdown")
        assert j["report"]["validation_status"] == "VALIDATED" and j["validation"]["status"] == "VALIDATED"
        assert md.headers["content-type"].startswith("text/markdown")
        assert md.text.startswith(f"# Investigation Report — {cid}") and "7/7 checks passed" in md.text

    def test_queue_priority_and_filters(self, store, india):
        t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
        for cid, action, score, minute in [("CASE-A", "CLEAR", 10.0, 0), ("CASE-B", "BLOCK", 80.0, 1),
                                           ("CASE-C", "ESCALATE", 60.0, 2), ("CASE-D", "ESCALATE", 70.0, 3),
                                           ("CASE-E", None, None, 4)]:
            store.create(make_record(cid, CaseStatus.AWAITING_REVIEW if action else CaseStatus.RECEIVED,
                                     action, score, created=t0.replace(minute=minute)))
        with TestClient(create_app(store=store, investigator_factory=make_factory(),
                                   feed_lookup=india.get_transaction)) as c:
            items = c.get("/api/v1/cases").json()["items"]
            assert [i["case_id"] for i in items][:4] == ["CASE-B", "CASE-D", "CASE-C", "CASE-A"]
            esc = c.get("/api/v1/cases?action=ESCALATE").json()
            assert esc["total"] == 2 and {i["case_id"] for i in esc["items"]} == {"CASE-C", "CASE-D"}
            page = c.get("/api/v1/cases?limit=2&offset=1").json()
            assert page["total"] >= 4 and [i["case_id"] for i in page["items"]] == ["CASE-D", "CASE-C"]
            assert "investigation" not in items[0]

    def test_decision_recorded_with_audit_context(self, store, india, tx_ids):
        with client_for(store, india) as c:
            body = post_alert(c, transaction_id=tx_ids[9]).json()
            cid, rec = body["case_id"], body["summary"]["recommended_action"]
            action = "CLEAR" if rec != "CLEAR" else "MONITOR"
            r = c.post(f"/api/v1/cases/{cid}/decision", json={
                "analyst_id": "analyst.one", "analyst_name": "Analyst One", "action": action,
                "rationale": "Reviewed counterparties."})
            assert r.status_code == 200, r.text
            d = r.json()["analyst_decision"]
            assert r.json()["status"] == "DECIDED"
            assert d["analyst_id"] == "analyst.one" and d["action"] == action
            assert d["system_recommended_action"] == rec and d["report_validation_status"] == "VALIDATED"
            assert d["agrees_with_system"] is (False if rec in ("BLOCK", "MONITOR", "ESCALATE", "CLEAR") else None)
            assert d["report_run_id"] == c.get(f"/api/v1/cases/{cid}/report").json()["report"]["agent5_run_id"]
            # revision: kept, linked, audited
            r2 = c.post(f"/api/v1/cases/{cid}/decision", json={
                "analyst_id": "analyst.two", "action": "ESCALATE", "rationale": "Second review."}).json()
            assert r2["analyst_decision"]["supersedes_decision_id"] == d["decision_id"]
            assert len(r2["decisions"]) == 2
            audit = c.get(f"/api/v1/cases/{cid}/audit").json()
        decisions = [e for e in audit if e["event_type"] == "ANALYST_DECISION"]
        assert [e["actor"] for e in decisions] == ["analyst.one", "analyst.two"]
        assert all(e["at_utc"] for e in decisions)

    def test_decision_validation_and_state_rules(self, store, india):
        store.create(make_record("CASE-NEW", CaseStatus.RECEIVED))
        with TestClient(create_app(store=store, investigator_factory=make_factory(),
                                   feed_lookup=india.get_transaction)) as c:
            ok = {"analyst_id": "a1", "action": "CLEAR", "rationale": "x"}
            assert c.post("/api/v1/cases/NOPE/decision", json=ok).status_code == 404
            for bad in ({**ok, "action": "HUMAN_REVIEW"}, {**ok, "rationale": ""}, {**ok, "analyst_id": "a b"},
                        {"action": "CLEAR", "rationale": "x"}):
                assert c.post("/api/v1/cases/CASE-NEW/decision", json=bad).status_code == 422
        # The RECEIVED case was re-queued by start(); its stub transaction cannot be
        # investigated, so it never reaches a decidable status.
        from src.api.case_schema import DecisionRequest
        from src.api.service import CaseService, Conflict

        assert store.get("CASE-NEW").status != CaseStatus.AWAITING_REVIEW
        with pytest.raises(Conflict):
            CaseService(store).decide("CASE-NEW", DecisionRequest(**ok))

    def test_cors_allow_list(self, store, india, monkeypatch):
        monkeypatch.setenv("SENTINEL_CORS_ORIGINS", "https://sentinel.example.app")
        with client_for(store, india) as c:
            ok = c.get("/health", headers={"Origin": "https://sentinel.example.app"})
            other = c.get("/health", headers={"Origin": "https://evil.example"})
        assert ok.headers.get("access-control-allow-origin") == "https://sentinel.example.app"
        assert "access-control-allow-origin" not in other.headers
        monkeypatch.setenv("SENTINEL_CORS_ORIGINS", "*")
        with pytest.raises(ValueError):
            create_app(store=store)


# ---------------------------------------------------------------------------
# Case store contract (JSON always; MongoDB when MONGODB_URI is configured)
# ---------------------------------------------------------------------------

def _mongo_store():
    try:  # only the MONGODB_* keys, like conftest does for NEO4J_* (no other secrets enter the tests)
        from dotenv import dotenv_values

        for k, v in dotenv_values(".env").items():
            if k.startswith("MONGODB_") and v and k not in os.environ:
                os.environ[k] = v
    except ImportError:
        pass
    if not os.environ.get("MONGODB_URI"):
        pytest.skip("MONGODB_URI not configured")
    db = f"sentinel_ai_test_{uuid4().hex[:10]}"
    s = MongoCaseStore(database=db)
    try:
        s.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MongoDB unreachable: {type(exc).__name__}")
    return s, db


@pytest.fixture(params=["json", "mongodb"])
def any_store(request, tmp_path):
    if request.param == "json":
        yield JsonCaseStore(tmp_path / "c")
        return
    s, db = _mongo_store()
    yield s
    s._client.drop_database(db)
    s.close()


class TestCaseStoreContract:
    def test_create_get_and_duplicate(self, any_store):
        any_store.create(make_record("CASE-1", CaseStatus.RECEIVED, key="K1"))
        assert any_store.get("CASE-1").case_id == "CASE-1"
        assert any_store.get("CASE-404") is None
        with pytest.raises(Exception):
            any_store.create(make_record("CASE-1", CaseStatus.RECEIVED))

    def test_conditional_update_and_append_only_audit(self, any_store):
        any_store.create(make_record("CASE-2", CaseStatus.RECEIVED))
        ev = AuditEvent(event_type=AuditEventType.INVESTIGATION_STARTED, actor="system")
        r = any_store.update("CASE-2", {"status": "INVESTIGATING"}, events=[ev],
                             require_status=[CaseStatus.RECEIVED])
        assert r.status == CaseStatus.INVESTIGATING and r.audit_trail[-1].event_id == ev.event_id
        # second transition with the same precondition is refused
        assert any_store.update("CASE-2", {"status": "INVESTIGATING"}, require_status=[CaseStatus.RECEIVED]) is None
        assert any_store.update("CASE-2", {"status": "X"}, require_fields={"analyst_decision.decision_id": "d"}) is None
        assert any_store.update("CASE-2", {"summary": CaseSummary(risk_score=5.0)},
                                require_fields={"analyst_decision": None}).summary.risk_score == 5.0
        assert any_store.update("CASE-404", {"status": "X"}) is None

    def test_transaction_key_lookup_skips_failed(self, any_store):
        any_store.create(make_record("CASE-F", CaseStatus.INVESTIGATION_FAILED, key="KX"))
        assert any_store.find_active_by_transaction_key("KX") is None
        any_store.create(make_record("CASE-G", CaseStatus.AWAITING_REVIEW, key="KX"))
        assert any_store.find_active_by_transaction_key("KX").case_id == "CASE-G"

    def test_list_order_and_unfinished(self, any_store):
        t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
        any_store.create(make_record("CASE-L1", CaseStatus.AWAITING_REVIEW, "MONITOR", 30.0, t0))
        any_store.create(make_record("CASE-L2", CaseStatus.AWAITING_REVIEW, "BLOCK", 90.0, t0.replace(minute=1)))
        any_store.create(make_record("CASE-L3", CaseStatus.RECEIVED, created=t0.replace(minute=2)))
        items, total = any_store.list()
        assert total == 3 and [i["case_id"] for i in items] == ["CASE-L2", "CASE-L1", "CASE-L3"]
        assert "investigation" not in items[0] and items[0]["transaction"]["raw_record_id"] == "T-CASE-L2"
        items, total = any_store.list(status=CaseStatus.RECEIVED)
        assert total == 1
        assert any_store.case_ids_with_status([CaseStatus.RECEIVED, CaseStatus.INVESTIGATING]) == ["CASE-L3"]
        assert any_store.ping()


def test_json_store_rejects_path_traversal(tmp_path):
    s = JsonCaseStore(tmp_path)
    assert s.get("../../etc/passwd") is None
