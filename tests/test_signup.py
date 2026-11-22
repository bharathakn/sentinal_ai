"""Public sign-up: private workspaces, no escalation, abuse limits."""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.agents.agent1.output_schema import Agent1Output, AgentStatus
from src.agents.agent3.output_schema import Agent3Output, Agent3Status
from src.agents.investigation import Investigator
from src.api import datasets
from src.api.app import create_app
from src.api.auth import AuthService, JsonAuthStore, MongoAuthStore, SignupRequest, User
from src.api.case_schema import AlertInfo, AlertSource, CaseRecord, CaseStatus, utcnow
from src.api.case_store import JsonCaseStore, MongoCaseStore
from src.api.run_store import run_store_for
from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

PW = "correct-horse-battery"
HEADER = ("transaction_id,timestamp,amount_inr,channel,sender_account_id,receiver_account_id,"
          "amount_ratio_vs_30d_avg,tx_frequency_24h,time_since_last_tx_sec\n")
CSV = (HEADER + "T1,2026-08-03T20:12:29+05:30,90000,UPI,ACC_A,ACC_B,9,1,3600\n").encode()
FEED_ROW = {"transaction_id": "TXN_FEED_1", "timestamp": "2026-08-03T20:12:29+05:30", "amount_inr": 5000,
            "channel": "UPI", "sender_account_id": "ACC_A", "receiver_account_id": "ACC_B"}


class FakeA1:
    screening_thresholds = {"xgb_threshold": 0.7, "if_threshold": 0.5}

    def score(self, tx):
        return Agent1Output(scored_at_utc=datetime.now(timezone.utc), status=AgentStatus.COMPLETE,
                            anomaly_score=0.9, isolation_score=0.6, combined_confidence=0.8)

    def screen(self, txs):
        return [{"transaction_id": t.raw_record_id, "combined_confidence": 0.8, "flagged": True} for t in txs]


def fake_a3(state):
    return {**state, "agent3_output": Agent3Output(status=Agent3Status.COMPLETE)}


@pytest.fixture()
def site(tmp_path):
    app = create_app(store=JsonCaseStore(tmp_path / "cases"), auth_store=JsonAuthStore(tmp_path / "auth.json"),
                     cookie_secure=False, feed_lookup=lambda _: dict(FEED_ROW),
                     investigator_factory=lambda: Investigator(agent1=FakeA1(), agent3=fake_a3))
    with TestClient(app) as first:
        def visitor(username=None, team=False):
            c = TestClient(app)  # its own cookie jar
            if team:
                app.state.auth.create_user(username, username.title(), PW)
                assert c.post("/api/v1/auth/login", json={"username": username, "password": PW}).status_code == 200
            elif username:
                r = signup(c, username)
                assert r.status_code == 201, r.text
            return c

        visitor.app = app
        visitor.anonymous = first
        yield visitor


def signup(c, username, **extra):
    return c.post("/api/v1/auth/signup",
                  json={"username": username, "display_name": "New Person", "password": PW, **extra})


def investigate(c):
    r = c.post("/api/v1/runs/upload?filename=mine.csv", content=CSV, headers={"Content-Type": "text/csv"})
    assert r.status_code == 202, r.text
    rid = r.json()["run_id"]
    for _ in range(300):
        run = c.get(f"/api/v1/runs/{rid}").json()
        if run["status"] in ("COMPLETED", "FAILED"):
            assert run["status"] == "COMPLETED"
            return rid, run["cases"][0]["case_id"]
        time.sleep(0.1)
    raise AssertionError("run did not finish")


class TestSignup:
    def test_signs_in_and_can_sign_in_again(self, site):
        c = site()
        r = signup(c, "  NewUser ")
        assert r.status_code == 201 and r.json()["username"] == "newuser"
        assert "httponly" in r.headers["set-cookie"].lower()
        assert c.get("/api/v1/auth/me").json()["username"] == "newuser"
        c.post("/api/v1/auth/logout")
        assert c.get("/api/v1/auth/me").status_code == 401
        assert c.post("/api/v1/auth/login", json={"username": "newuser", "password": PW}).status_code == 200

    def test_is_always_a_private_account(self, site):
        site("alice")
        assert site.app.state.auth.store.get_user("alice").workspace == "alice"

    @pytest.mark.parametrize("field", ["self_registered", "active", "role", "workspace"])
    def test_account_type_cannot_be_requested(self, site, field):
        assert signup(site(), "mallory", **{field: False}).status_code == 422

    @pytest.mark.parametrize("name", ["system", "ingest-api-key", "demo-seed", "admin", "SYSTEM"])
    def test_audit_actor_names_are_reserved(self, site, name):
        assert signup(site(), name).status_code == 409

    def test_cannot_take_over_an_existing_account(self, site):
        site("boss", team=True)
        before = site.app.state.auth.store.get_user("boss")
        attacker = site()
        assert signup(attacker, "BOSS", password="attacker-password").status_code == 409
        assert site.app.state.auth.store.get_user("boss") == before
        assert attacker.get("/api/v1/auth/me").status_code == 401

    @pytest.mark.parametrize("body", [{"password": "short"}, {"password": " padded-password "}, {"username": "a b"},
                                      {"display_name": "   "}, {"username": "ab"}])
    def test_bad_input(self, site, body):
        payload = {"username": "someone", "display_name": "Some One", "password": PW, **body}
        assert site().post("/api/v1/auth/signup", json=payload).status_code == 422

    def test_switch_off(self, site, monkeypatch):
        monkeypatch.setenv("SENTINEL_ALLOW_SIGNUP", "false")
        site.app.state.auth.signup_open = False
        assert signup(site(), "late").status_code == 403
        assert site().get("/health").json()["signup_open"] is False

    def test_hourly_limit(self, site):
        site.app.state.auth.signups_per_hour = 2
        assert [signup(site(), f"user{i}").status_code for i in range(3)] == [201, 201, 429]

    def test_accounts_from_before_signup_stay_team_accounts(self):
        old = User.model_validate({"username": "older", "display_name": "Older", "password_hash": "x"})
        assert old.workspace is None

    def test_promote(self, site):
        owner, other = site("owner"), site("helper")
        _, case_id = investigate(owner)
        assert other.get(f"/api/v1/cases/{case_id}").status_code == 404
        site.app.state.auth.promote("helper")
        assert other.get(f"/api/v1/cases/{case_id}").status_code == 200


class TestWorkspaces:
    def test_every_case_and_run_route_is_private(self, site):
        owner, stranger = site("owner"), site("stranger")
        run_id, case_id = investigate(owner)
        checked = 0
        for path, methods in site.app.openapi()["paths"].items():
            if "{case_id}" not in path and "{run_id}" not in path:
                continue
            url = re.sub(r"\{case_id\}", case_id, path).replace("{run_id}", run_id)
            for method in methods:
                kw = {"json": {"action": "CLEAR", "rationale": "hijack"}} if method == "post" else {}
                r = stranger.request(method.upper(), url, **kw)
                assert r.status_code == 404, f"{method} {path} leaked: {r.status_code}"
                checked += 1
        assert checked >= 7
        assert owner.get(f"/api/v1/cases/{case_id}").json()["decisions"] == []

    def test_lists_show_only_own_work(self, site):
        owner, stranger = site("owner"), site("stranger")
        run_id, case_id = investigate(owner)
        assert [c["case_id"] for c in owner.get("/api/v1/cases").json()["items"]] == [case_id]
        assert [r["run_id"] for r in owner.get("/api/v1/runs").json()["items"]] == [run_id]
        assert stranger.get("/api/v1/cases").json()["total"] == 0
        assert stranger.get("/api/v1/runs").json()["items"] == []

    def test_owner_can_resolve_and_team_sees_everything(self, site):
        owner, boss = site("owner"), site("boss", team=True)
        run_id, case_id = investigate(owner)
        assert boss.get("/api/v1/cases").json()["total"] == 1
        assert boss.get(f"/api/v1/runs/{run_id}").status_code == 200
        r = owner.post(f"/api/v1/cases/{case_id}/decision", json={"action": "ESCALATE", "rationale": "mine"})
        assert r.json()["analyst_decision"]["analyst_id"] == "owner"

    def test_same_alert_never_returns_someone_elses_case(self, site):
        ids = []
        for c in (site("boss", team=True), site("alice"), site("bob")):
            r = c.post("/api/v1/alerts?wait=true", json={"transaction_id": "TXN_FEED_1"})
            assert r.json()["duplicate"] is False, r.text
            ids.append(r.json()["case_id"])
        assert len(set(ids)) == 3

    def test_private_account_cannot_post_raw_transactions(self, site):
        tx = IndiaSyntheticAdapter.from_row(FEED_ROW).model_dump(mode="json")
        assert site("alice").post("/api/v1/alerts", json={"transaction": tx}).status_code == 403
        assert site("boss", team=True).post("/api/v1/alerts", json={"transaction": tx}).status_code == 202


class TestAbuseLimits:
    def test_daily_allowance_is_per_account(self, site):
        site.app.state.runs.allowance.limit = 1
        alice, bob = site("alice"), site("bob")
        investigate(alice)
        r = alice.post("/api/v1/runs/upload", content=CSV, headers={"Content-Type": "text/csv"})
        assert r.status_code == 429 and "today" in r.json()["detail"]
        investigate(bob)

    def test_one_running_investigation_per_private_account(self, site):
        alice = site("alice")
        site.app.state.runs._active_by["alice"] = 1
        assert alice.post("/api/v1/runs/upload", content=CSV, headers={"Content-Type": "text/csv"}).status_code == 429

    def test_big_bodies_refused_before_sign_in(self, site):
        for path in ("/api/v1/auth/login", "/api/v1/auth/signup", "/api/v1/alerts"):
            r = site.anonymous.post(path, content=b'{"a":"' + b"x" * 200_000 + b'"}',
                                    headers={"Content-Type": "application/json"})
            assert r.status_code == 413, path

    @pytest.mark.parametrize("bomb", [b"[" + b"{}," * 40000 + b"{}]", b"[" + b"[]," * 40000 + b"[]]",
                                      b"a" + b"," * 700000 + b"\n"])
    def test_parser_bombs_refused(self, bomb):
        with pytest.raises(datasets.DatasetError, match="more than"):
            datasets.parse_upload(bomb, "bomb")

    def test_ordinary_large_file_still_accepted(self):
        rows = "".join(f"T{i},2026-08-03T20:12:29+05:30,90000,UPI,A,B,9,1,3600\n" for i in range(10000))
        assert len(datasets.parse_upload((HEADER + rows).encode(), "ok.csv").rows) == 10000


@contextmanager
def atlas_database():
    try:
        from dotenv import dotenv_values

        for k, v in dotenv_values(".env").items():
            if k.startswith("MONGODB_") and v and k not in os.environ:
                os.environ[k] = v
    except ImportError:
        pass
    if not os.environ.get("MONGODB_URI"):
        pytest.skip("MONGODB_URI not configured")
    db = f"sentinel_ai_test_{uuid4().hex[:10]}"
    store = MongoCaseStore(database=db)
    try:
        store.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MongoDB unreachable: {type(exc).__name__}")
    try:
        yield store, db
    finally:
        store._client.drop_database(db)
        store.close()


def test_mongo_workspaces_live():
    with atlas_database() as (cases, db):
        auth = AuthService(MongoAuthStore(database=db, client=cases._client))
        auth.signup(SignupRequest(username="alice", display_name="Alice", password=PW))
        assert auth.store.get_user("alice").workspace == "alice"
        with pytest.raises(ValueError):
            auth.signup(SignupRequest(username="alice", display_name="Again", password=PW))
        now = utcnow()
        runs = run_store_for(cases)
        for who in ("alice", "bob"):
            cases.create(CaseRecord(case_id=f"CASE-{who}", owner=who, transaction_key=who,
                                    status=CaseStatus.AWAITING_REVIEW, created_at_utc=now, updated_at_utc=now,
                                    alert=AlertInfo(source=AlertSource.API, received_at_utc=now), transaction={}))
            runs.create({"run_id": f"RUN-{who}", "created_by": who, "created_at_utc": now.isoformat()})
        items, total = cases.list(owner="alice")
        assert total == 1 and items[0]["case_id"] == "CASE-alice"
        assert [r["run_id"] for r in runs.list(owner="alice")] == ["RUN-alice"]
        assert cases.list()[1] == 2
