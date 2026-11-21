"""Phase 13.1 — analyst sign-in: passwords, sessions, cookies, lockout, revocation."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import (
    COOKIE_NAME, AuthError, AuthService, JsonAuthStore, LoginRequest, MongoAuthStore, check_password_policy,
    hash_password, token_hash, utcnow, verify_password,
)
from src.api.case_store import JsonCaseStore

PW = "correct-horse-battery"


@pytest.fixture()
def auth_store(tmp_path):
    return JsonAuthStore(tmp_path / "auth.json")


@pytest.fixture()
def client(tmp_path, auth_store):
    app = create_app(store=JsonCaseStore(tmp_path / "cases"), auth_store=auth_store, cookie_secure=False,
                     investigator_factory=lambda: None, feed_lookup=lambda _: None)
    with TestClient(app) as c:
        c.auth_service = app.state.auth
        c.auth_service.create_user("alice", "Alice Rao", PW)
        yield c


def login(c, username="alice", password=PW, **kw):
    return c.post("/api/v1/auth/login", json={"username": username, "password": password, **kw})


class TestPasswords:
    def test_hash_roundtrip_and_salt(self):
        h1, h2 = hash_password(PW), hash_password(PW)
        assert h1 != h2 and h1.startswith("scrypt$") and PW not in h1
        assert verify_password(PW, h1) and not verify_password(PW + "x", h1)
        assert not verify_password(PW, "garbage") and not verify_password(PW, "md5$a$b")

    @pytest.mark.parametrize("pw", ["short", " leading-space-pw", "trailing-space-pw ", " " * 12])
    def test_policy(self, pw):
        with pytest.raises(ValueError):
            check_password_policy(pw)


class TestLogin:
    def test_login_sets_secure_session_cookie(self, client):
        r = login(client)
        assert r.status_code == 200 and r.json() == {"username": "alice", "display_name": "Alice Rao"}
        cookie = r.headers["set-cookie"].lower()
        assert f"{COOKIE_NAME}=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
        assert f"max-age={30 * 86400}" in cookie
        assert client.get("/api/v1/auth/me").json()["username"] == "alice"

    def test_secure_flag_by_default(self, tmp_path, auth_store, monkeypatch):
        monkeypatch.delenv("SENTINEL_COOKIE_SECURE", raising=False)
        app = create_app(store=JsonCaseStore(tmp_path / "c"), auth_store=auth_store,
                         investigator_factory=lambda: None)
        with TestClient(app) as c:
            app.state.auth.create_user("bob", "Bob", PW)
            r = login(c, "bob")
        assert "secure" in r.headers["set-cookie"].lower()

    def test_without_remember_is_browser_session(self, client):
        r = login(client, remember=False)
        assert "max-age" not in r.headers["set-cookie"].lower()
        s = next(iter(client.auth_service.store._load()["sessions"].values()))
        assert s["remember"] is False

    def test_username_case_insensitive(self, client):
        assert login(client, "  ALICE ").status_code == 200

    def test_same_error_for_unknown_user_and_wrong_password(self, client):
        a, b = login(client, password="wrong-password-1"), login(client, username="nobody")
        assert a.status_code == b.status_code == 401 and a.json() == b.json()

    def test_lockout_after_five_failures(self, client):
        for _ in range(5):
            assert login(client, password="wrong-password-1").status_code == 401
        r = login(client)  # even the right password is refused while locked
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
        client.auth_service.create_user("carol", "Carol", PW)
        assert login(client, "carol").status_code == 200  # other users unaffected

    def test_success_resets_failure_count(self, client):
        for _ in range(4):
            login(client, password="wrong-password-1")
        assert login(client).status_code == 200
        for _ in range(4):
            login(client, password="wrong-password-1")
        assert login(client).status_code == 200


class TestAccessControl:
    @pytest.mark.parametrize("method,path", [
        ("get", "/api/v1/cases"), ("get", "/api/v1/cases/CASE-X"), ("get", "/api/v1/cases/CASE-X/report"),
        ("get", "/api/v1/cases/CASE-X/audit"), ("post", "/api/v1/cases/CASE-X/decision"),
        ("post", "/api/v1/alerts"), ("get", "/api/v1/auth/me"),
    ])
    def test_endpoints_need_sign_in(self, client, method, path):
        kw = {"json": {"action": "CLEAR", "rationale": "x"}} if "decision" in path else (
            {"json": {"transaction_id": "T1"}} if "alerts" in path else {})
        assert getattr(client, method)(path, **kw).status_code == 401

    def test_health_is_public(self, client):
        assert client.get("/health").status_code == 200

    def test_forged_cookie_rejected(self, client):
        client.cookies.set(COOKIE_NAME, "not-a-real-token")
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_logout_revokes_session(self, client):
        login(client)
        token = client.cookies.get(COOKIE_NAME)
        assert client.post("/api/v1/auth/logout").status_code == 204
        client.cookies.set(COOKIE_NAME, token)  # replaying the old cookie does not work
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_disabled_user_signed_out_and_blocked(self, client):
        login(client)
        client.auth_service.set_active("alice", False)
        assert client.get("/api/v1/auth/me").status_code == 401
        assert login(client).status_code == 401
        client.auth_service.set_active("alice", True)
        assert login(client).status_code == 200


class TestSessions:
    def test_only_token_hash_stored(self, client, tmp_path):
        login(client)
        token = client.cookies.get(COOKIE_NAME)
        raw = (tmp_path / "auth.json").read_text()
        assert token not in raw and token_hash(token) in raw and PW not in raw

    def test_idle_expiry(self, client):
        login(client)
        h = token_hash(client.cookies.get(COOKIE_NAME))
        client.auth_service.store.update_session(h, {"expires_at_utc": utcnow() - timedelta(seconds=1)})
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.auth_service.store.get_session(h) is None  # cleaned up

    def test_sliding_expiry_capped_at_absolute(self, auth_store):
        svc = AuthService(auth_store, idle_days=7, max_days=30)
        svc.create_user("dave", "Dave", PW)
        token, _, s = svc.login(LoginRequest(username="dave", password=PW))
        assert s.expires_at_utc - s.created_at_utc == timedelta(days=7)
        # used again after 10 minutes: idle window restarts
        auth_store.update_session(s.token_hash, {"last_seen_at_utc": utcnow() - timedelta(minutes=10),
                                                 "expires_at_utc": utcnow() + timedelta(days=1)})
        svc.authenticate(token)
        s2 = auth_store.get_session(s.token_hash)
        assert s2.expires_at_utc > utcnow() + timedelta(days=6, hours=23)
        # near the absolute limit, the extension stops at it
        cap = utcnow() + timedelta(hours=2)
        auth_store.update_session(s.token_hash, {"last_seen_at_utc": utcnow() - timedelta(minutes=10),
                                                 "absolute_expires_at_utc": cap})
        svc.authenticate(token)
        assert auth_store.get_session(s.token_hash).expires_at_utc == cap

    def test_short_session_without_remember(self, auth_store):
        svc = AuthService(auth_store)
        svc.create_user("erin", "Erin", PW)
        _, _, s = svc.login(LoginRequest(username="erin", password=PW, remember=False))
        assert s.absolute_expires_at_utc - s.created_at_utc == timedelta(hours=12)

    def test_password_change(self, client, tmp_path):
        login(client)
        other = TestClient(client.app)  # second device, same user
        other.post("/api/v1/auth/login", json={"username": "alice", "password": PW})
        assert other.get("/api/v1/auth/me").status_code == 200
        bad = client.post("/api/v1/auth/password", json={"current_password": "nope-nope-nope", "new_password": "x" * 12})
        assert bad.status_code == 401
        weak = client.post("/api/v1/auth/password", json={"current_password": PW, "new_password": "short"})
        assert weak.status_code == 422
        new = "new-horse-battery-2"
        assert client.post("/api/v1/auth/password", json={"current_password": PW, "new_password": new}).status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 200   # this device stays signed in
        assert other.get("/api/v1/auth/me").status_code == 401    # other devices signed out
        assert login(client, password=PW).status_code == 401
        assert login(client, password=new).status_code == 200


def test_manage_users_cli(tmp_path):
    env = {**os.environ, "SENTINEL_CASE_STORE": "json", "SENTINEL_AUTH_FILE": str(tmp_path / "auth.json"),
           "PYTHONPATH": "."}

    def run(*args, stdin=None):
        return subprocess.run([sys.executable, "scripts/manage_users.py", *args], input=stdin, env=env,
                              capture_output=True, text=True, timeout=60)

    r = run("create", "Frank", "--name", "Frank Ito", "--password-stdin", stdin=PW + "\n")
    assert r.returncode == 0, r.stderr
    assert "frank" in run("list").stdout
    assert run("create", "frank", "--name", "Dup", "--password-stdin", stdin=PW + "\n").returncode != 0
    assert run("create", "gina", "--name", "Gina", "--password-stdin", stdin="short\n").returncode != 0
    assert run("disable", "frank").returncode == 0 and "DISABLED" in run("list").stdout
    store = JsonAuthStore(tmp_path / "auth.json")
    assert verify_password(PW, store.get_user("frank").password_hash)


def test_mongo_auth_store_live():
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
    store = MongoAuthStore(database=db)
    try:
        store._client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MongoDB unreachable: {type(exc).__name__}")
    try:
        svc = AuthService(store)
        svc.create_user("hank", "Hank", PW)
        with pytest.raises(ValueError):
            svc.create_user("hank", "Hank", PW)
        token, user, s = svc.login(LoginRequest(username="hank", password=PW))
        assert svc.authenticate(token)[0].username == "hank"
        idx = store._sessions.index_information()
        assert any(v.get("expireAfterSeconds") == 0 for v in idx.values())  # TTL cleanup of expired sessions
        svc.set_active("hank", False)
        with pytest.raises(AuthError):
            svc.authenticate(token)
        with pytest.raises(KeyError):
            store.update_user("nobody", {"active": True})
    finally:
        store._client.drop_database(db)
        store.close()
