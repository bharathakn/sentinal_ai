"""
Sentinel AI — analyst sign-in (Phase 13.1).

Design goal: real authentication that analysts rarely notice.

* **Accounts** are created by an administrator (``scripts/manage_users.py``);
  there is no public sign-up. Usernames are lower-case.
* **Passwords** are hashed with scrypt (stdlib; n=2**14, r=8, p=1, 16-byte
  salt). Minimum length 10.
* **Sessions** are server-side. The browser holds a random 256-bit token in an
  HttpOnly, SameSite=Lax cookie (Secure by default); the store keeps only its
  SHA-256. A session expires after ``SENTINEL_SESSION_IDLE_DAYS`` (default 7)
  without use and at most ``SENTINEL_SESSION_MAX_DAYS`` (default 30) after
  sign-in, so an analyst who works daily signs in about once a month.
  "Keep me signed in" off → 12 hours idle and a browser-session cookie.
* **Revocation**: sign-out deletes the session; disabling a user or changing a
  password deletes the user's other sessions.
* **Brute force**: 5 failed sign-ins for a username within 15 minutes lock that
  username for the rest of the window (HTTP 429). Errors never reveal whether
  the username exists.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

COOKIE_NAME = "sentinel_session"
MIN_PASSWORD_LENGTH = 10
_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._@\-]{1,63}$"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Passwords and tokens
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_hex(16))  # equalises timing for unknown usernames


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password.strip() != password or not password.strip():
        raise ValueError("Password must not start or end with spaces.")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    display_name: str = Field(min_length=1, max_length=128)
    password_hash: str
    active: bool = True
    created_at_utc: datetime = Field(default_factory=utcnow)
    password_changed_at_utc: datetime = Field(default_factory=utcnow)
    last_login_at_utc: Optional[datetime] = None


class Session(BaseModel):
    token_hash: str
    username: str
    created_at_utc: datetime
    last_seen_at_utc: datetime
    expires_at_utc: datetime
    absolute_expires_at_utc: datetime
    remember: bool = True


class PublicUser(BaseModel):
    username: str
    display_name: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    remember: bool = Field(default=True, description="Keep me signed in on this device.")

    @field_validator("username")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

class AuthStore(Protocol):
    def get_user(self, username: str) -> Optional[User]: ...
    def create_user(self, user: User) -> None: ...
    def update_user(self, username: str, fields: dict[str, Any]) -> None: ...
    def list_users(self) -> list[User]: ...
    def create_session(self, session: Session) -> None: ...
    def get_session(self, token_hash: str) -> Optional[Session]: ...
    def update_session(self, token_hash: str, fields: dict[str, Any]) -> None: ...
    def delete_session(self, token_hash: str) -> None: ...
    def delete_user_sessions(self, username: str, except_hash: Optional[str] = None) -> None: ...


class JsonAuthStore:
    """Development store: one JSON file (users + sessions)."""

    def __init__(self, path: Optional[os.PathLike | str] = None) -> None:
        self._path = Path(path or os.environ.get("SENTINEL_AUTH_FILE", "var/auth.json"))
        self._lock = threading.RLock()

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except FileNotFoundError:
            return {"users": {}, "sessions": {}}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)

    def get_user(self, username):
        d = self._load()["users"].get(username)
        return User.model_validate(d) if d else None

    def create_user(self, user):
        with self._lock:
            data = self._load()
            if user.username in data["users"]:
                raise ValueError(f"User {user.username} already exists.")
            data["users"][user.username] = user.model_dump(mode="json")
            self._save(data)

    def update_user(self, username, fields):
        with self._lock:
            data = self._load()
            if username not in data["users"]:
                raise KeyError(username)
            data["users"][username].update({k: _j(v) for k, v in fields.items()})
            self._save(data)

    def list_users(self):
        return [User.model_validate(u) for u in sorted(self._load()["users"].values(), key=lambda u: u["username"])]

    def create_session(self, session):
        with self._lock:
            data = self._load()
            now = utcnow()
            data["sessions"] = {k: v for k, v in data["sessions"].items()  # drop expired
                                if datetime.fromisoformat(v["expires_at_utc"].replace("Z", "+00:00")) > now}
            data["sessions"][session.token_hash] = session.model_dump(mode="json")
            self._save(data)

    def get_session(self, token_hash):
        d = self._load()["sessions"].get(token_hash)
        return Session.model_validate(d) if d else None

    def update_session(self, token_hash, fields):
        with self._lock:
            data = self._load()
            if token_hash in data["sessions"]:
                data["sessions"][token_hash].update({k: _j(v) for k, v in fields.items()})
                self._save(data)

    def delete_session(self, token_hash):
        with self._lock:
            data = self._load()
            if data["sessions"].pop(token_hash, None) is not None:
                self._save(data)

    def delete_user_sessions(self, username, except_hash=None):
        with self._lock:
            data = self._load()
            data["sessions"] = {k: v for k, v in data["sessions"].items()
                                if v["username"] != username or k == except_hash}
            self._save(data)


def _j(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat().replace("+00:00", "Z")
    return v


class MongoAuthStore:
    """Hosted store: collections ``users`` and ``sessions`` (TTL index removes expired sessions)."""

    def __init__(self, uri: Optional[str] = None, database: Optional[str] = None, client: Any = None) -> None:
        if client is None:
            from pymongo import MongoClient

            uri = uri or os.environ.get("MONGODB_URI")
            if not uri:
                from .case_store import CaseStoreError

                raise CaseStoreError("SENTINEL_CASE_STORE=mongodb needs MONGODB_URI.")
            client = MongoClient(uri, serverSelectionTimeoutMS=8000, appname="sentinel-ai", tz_aware=True)
        self._client = client
        db = client[database or os.environ.get("MONGODB_DATABASE", "sentinel_ai")]
        self._users, self._sessions = db["users"], db["sessions"]
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if not self._indexed:
            self._sessions.create_index("expires_at_utc", expireAfterSeconds=0)
            self._sessions.create_index("username")
            self._indexed = True

    @staticmethod
    def _native(model: BaseModel) -> dict:
        return model.model_dump()  # datetimes stay BSON dates (needed by the TTL index)

    def get_user(self, username):
        d = self._users.find_one({"_id": username})
        return User.model_validate(d) if d else None

    def create_user(self, user):
        from pymongo.errors import DuplicateKeyError

        try:
            self._users.insert_one({"_id": user.username, **self._native(user)})
        except DuplicateKeyError as exc:
            raise ValueError(f"User {user.username} already exists.") from exc

    def update_user(self, username, fields):
        if self._users.update_one({"_id": username}, {"$set": fields}).matched_count == 0:
            raise KeyError(username)

    def list_users(self):
        return [User.model_validate(d) for d in self._users.find().sort("_id", 1)]

    def create_session(self, session):
        self._ensure_indexes()
        self._sessions.insert_one({"_id": session.token_hash, **self._native(session)})

    def get_session(self, token_hash):
        d = self._sessions.find_one({"_id": token_hash})
        return Session.model_validate(d) if d else None

    def update_session(self, token_hash, fields):
        self._sessions.update_one({"_id": token_hash}, {"$set": fields})

    def delete_session(self, token_hash):
        self._sessions.delete_one({"_id": token_hash})

    def delete_user_sessions(self, username, except_hash=None):
        flt: dict[str, Any] = {"username": username}
        if except_hash:
            flt["_id"] = {"$ne": except_hash}
        self._sessions.delete_many(flt)

    def close(self) -> None:
        self._client.close()


def auth_store_from_env() -> AuthStore:
    name = os.environ.get("SENTINEL_CASE_STORE", "json").strip().lower()
    return MongoAuthStore() if name == "mongodb" else JsonAuthStore()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Invalid credentials or session (message is safe to show)."""


class LoginLocked(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many failed sign-in attempts. Try again later.")
        self.retry_after = retry_after


class _Throttle:
    def __init__(self, max_failures: int = 5, window_seconds: int = 900) -> None:
        self.max, self.window = max_failures, window_seconds
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._fails.get(key, []) if now - t < self.window]
            self._fails[key] = recent
            if len(recent) >= self.max:
                raise LoginLocked(int(self.window - (now - recent[0])) + 1)

    def fail(self, key: str) -> None:
        with self._lock:
            self._fails.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


class AuthService:
    TOUCH_INTERVAL = timedelta(minutes=5)

    def __init__(self, store: AuthStore, idle_days: Optional[float] = None, max_days: Optional[float] = None,
                 short_idle_hours: float = 12) -> None:
        self.store = store
        self.idle = timedelta(days=idle_days if idle_days is not None
                              else float(os.environ.get("SENTINEL_SESSION_IDLE_DAYS", "7")))
        self.max_age = timedelta(days=max_days if max_days is not None
                                 else float(os.environ.get("SENTINEL_SESSION_MAX_DAYS", "30")))
        self.short_idle = timedelta(hours=short_idle_hours)
        self.throttle = _Throttle()

    # -- user administration (CLI) --------------------------------------
    def create_user(self, username: str, display_name: str, password: str) -> User:
        check_password_policy(password)
        user = User(username=username.strip().lower(), display_name=display_name.strip(),
                    password_hash=hash_password(password))
        self.store.create_user(user)
        return user

    def set_password(self, username: str, password: str, keep_session: Optional[str] = None) -> None:
        check_password_policy(password)
        self.store.update_user(username, {"password_hash": hash_password(password),
                                          "password_changed_at_utc": utcnow()})
        self.store.delete_user_sessions(username, except_hash=keep_session)

    def set_active(self, username: str, active: bool) -> None:
        self.store.update_user(username, {"active": active})
        if not active:
            self.store.delete_user_sessions(username)

    # -- sign-in --------------------------------------------------------
    def login(self, req: LoginRequest) -> tuple[str, User, Session]:
        self.throttle.check(req.username)
        user = self.store.get_user(req.username)
        ok = verify_password(req.password, user.password_hash if user else _DUMMY_HASH)
        if not (user and ok and user.active):
            self.throttle.fail(req.username)
            raise AuthError("Incorrect username or password.")
        self.throttle.reset(req.username)
        now = utcnow()
        token = new_token()
        absolute = now + (self.max_age if req.remember else self.short_idle)
        session = Session(token_hash=token_hash(token), username=user.username, created_at_utc=now,
                          last_seen_at_utc=now, expires_at_utc=min(now + (self.idle if req.remember
                                                                         else self.short_idle), absolute),
                          absolute_expires_at_utc=absolute, remember=req.remember)
        self.store.create_session(session)
        self.store.update_user(user.username, {"last_login_at_utc": now})
        return token, user, session

    def authenticate(self, token: Optional[str]) -> tuple[User, Session]:
        if not token:
            raise AuthError("Sign in required.")
        h = token_hash(token)
        session = self.store.get_session(h)
        now = utcnow()
        if session is None or session.expires_at_utc <= now:
            if session is not None:
                self.store.delete_session(h)
            raise AuthError("Session expired. Please sign in again.")
        user = self.store.get_user(session.username)
        if user is None or not user.active:
            self.store.delete_session(h)
            raise AuthError("Account disabled.")
        if now - session.last_seen_at_utc >= self.TOUCH_INTERVAL:  # sliding expiry, few writes
            expires = min(now + (self.idle if session.remember else self.short_idle), session.absolute_expires_at_utc)
            self.store.update_session(h, {"last_seen_at_utc": now, "expires_at_utc": expires})
        return user, session

    def logout(self, token: Optional[str]) -> None:
        if token:
            self.store.delete_session(token_hash(token))

    def change_password(self, user: User, session: Session, req: PasswordChangeRequest) -> None:
        if not verify_password(req.current_password, user.password_hash):
            raise AuthError("Current password is incorrect.")
        self.set_password(user.username, req.new_password, keep_session=session.token_hash)


__all__ = ["AuthService", "AuthStore", "AuthError", "LoginLocked", "JsonAuthStore", "MongoAuthStore",
           "auth_store_from_env", "User", "Session", "PublicUser", "LoginRequest", "PasswordChangeRequest",
           "COOKIE_NAME", "hash_password", "verify_password"]
