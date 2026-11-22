"""
Sentinel AI — Phase 13: case store.

One interface, two backends selected by ``SENTINEL_CASE_STORE``:

* ``json``    — one JSON file per case under ``SENTINEL_CASE_DIR`` (default
  ``var/cases``). Local development only: Render's disk is wiped on every
  deploy and restart.
* ``mongodb`` — MongoDB Atlas (``MONGODB_URI``, ``MONGODB_DATABASE`` default
  ``sentinel_ai``, collection ``cases``). Required for the hosted deployment.

Both store ``CaseRecord.model_dump(mode="json")`` with ``case_id`` as the key.
Updates are conditional (``require_status`` / ``require_fields``) so that a
status transition or a decision revision cannot be applied twice. Audit events
and decisions are only ever appended.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

from .case_schema import AnalystDecision, AuditEvent, CaseRecord, CaseStatus, utcnow

#: Fields left out of queue listings (large).
_LIST_EXCLUDE = ("investigation", "audit_trail", "decisions", "transaction")
_TX_LIST_FIELDS = ("raw_record_id", "amount", "currency")


class CaseStoreError(Exception):
    """The case store is unreachable or misconfigured."""


class CaseStore(Protocol):
    backend_name: str

    def ping(self) -> bool: ...
    def create(self, record: CaseRecord) -> None: ...
    def get(self, case_id: str) -> Optional[CaseRecord]: ...
    def find_active_by_transaction_key(self, key: str) -> Optional[CaseRecord]: ...
    def update(self, case_id: str, fields: dict[str, Any], events: Iterable[AuditEvent] = (),
               decision: Optional[AnalystDecision] = None,
               require_status: Optional[Iterable[CaseStatus]] = None,
               require_fields: Optional[dict[str, Any]] = None) -> Optional[CaseRecord]: ...
    def list(self, status: Optional[CaseStatus] = None, action: Optional[str] = None,
             limit: int = 50, offset: int = 0, owner: Optional[str] = None) -> tuple[list[dict], int]: ...
    def case_ids_with_status(self, statuses: Iterable[CaseStatus]) -> list[str]: ...


def _now_json() -> str:
    """UTC now in the same JSON form pydantic writes (…Z), so stored times sort consistently."""
    return utcnow().isoformat().replace("+00:00", "Z")


def _dump(v: Any) -> Any:
    return v.model_dump(mode="json") if hasattr(v, "model_dump") else v


def _get_path(doc: dict, dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _sort_key(doc: dict):
    s = doc.get("summary") or {}
    score = s.get("risk_score")
    return (-(s.get("priority_rank") or 0), -(score if score is not None else -1.0), doc.get("created_at_utc") or "")


def _list_view(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k not in _LIST_EXCLUDE and k != "_id"}
    tx = doc.get("transaction") or {}
    out["transaction"] = {k: tx.get(k) for k in _TX_LIST_FIELDS}
    return out


# ---------------------------------------------------------------------------
# JSON files (development)
# ---------------------------------------------------------------------------

class JsonCaseStore:
    backend_name = "json"

    def __init__(self, directory: Optional[os.PathLike | str] = None) -> None:
        self._dir = Path(directory or os.environ.get("SENTINEL_CASE_DIR", "var/cases"))
        self._lock = threading.RLock()

    def _path(self, case_id: str) -> Path:
        if not case_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid case id")
        return self._dir / f"{case_id}.json"

    def _read(self, path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return None

    def _write(self, doc: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(doc["case_id"])
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False))
        os.replace(tmp, path)  # atomic: readers never see a half-written case

    def _all(self) -> list[dict]:
        if not self._dir.is_dir():
            return []
        return [d for p in self._dir.glob("*.json") if (d := self._read(p)) is not None]

    def ping(self) -> bool:
        self._dir.mkdir(parents=True, exist_ok=True)
        return os.access(self._dir, os.W_OK)

    def create(self, record: CaseRecord) -> None:
        with self._lock:
            if self._path(record.case_id).exists():
                raise ValueError(f"case {record.case_id} already exists")
            self._write(record.model_dump(mode="json"))

    def get(self, case_id: str) -> Optional[CaseRecord]:
        try:
            doc = self._read(self._path(case_id))
        except ValueError:
            return None
        return CaseRecord.model_validate(doc) if doc else None

    def find_active_by_transaction_key(self, key: str) -> Optional[CaseRecord]:
        with self._lock:
            docs = [d for d in self._all() if d.get("transaction_key") == key
                    and d.get("status") != CaseStatus.INVESTIGATION_FAILED.value]
        docs.sort(key=lambda d: d.get("created_at_utc") or "")
        return CaseRecord.model_validate(docs[0]) if docs else None

    def update(self, case_id, fields, events=(), decision=None, require_status=None, require_fields=None):
        with self._lock:
            try:
                doc = self._read(self._path(case_id))
            except ValueError:
                return None
            if doc is None:
                return None
            if require_status is not None and doc.get("status") not in {s.value for s in require_status}:
                return None
            for k, v in (require_fields or {}).items():
                if _get_path(doc, k) != v:
                    return None
            for k, v in fields.items():
                doc[k] = _dump(v)
            doc.setdefault("audit_trail", []).extend(_dump(e) for e in events)
            if decision is not None:
                doc.setdefault("decisions", []).append(_dump(decision))
            doc["updated_at_utc"] = _now_json()
            self._write(doc)
            return CaseRecord.model_validate(doc)

    def list(self, status=None, action=None, limit=50, offset=0, owner=None):
        docs = self._all()
        if owner is not None:
            docs = [d for d in docs if d.get("owner") == owner]
        if status is not None:
            docs = [d for d in docs if d.get("status") == status.value]
        if action is not None:
            docs = [d for d in docs if (d.get("summary") or {}).get("recommended_action") == action]
        docs.sort(key=_sort_key)
        return [_list_view(d) for d in docs[offset:offset + limit]], len(docs)

    def case_ids_with_status(self, statuses):
        wanted = {s.value for s in statuses}
        docs = sorted((d for d in self._all() if d.get("status") in wanted), key=lambda d: d.get("created_at_utc") or "")
        return [d["case_id"] for d in docs]


# ---------------------------------------------------------------------------
# MongoDB Atlas (hosted deployment)
# ---------------------------------------------------------------------------

class MongoCaseStore:
    backend_name = "mongodb"

    def __init__(self, uri: Optional[str] = None, database: Optional[str] = None,
                 collection: str = "cases", client: Any = None) -> None:
        uri = uri or os.environ.get("MONGODB_URI")
        if client is None and not uri:
            raise CaseStoreError("SENTINEL_CASE_STORE=mongodb needs MONGODB_URI.")
        if client is None:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=8000, appname="sentinel-ai", tz_aware=True)
        self._client = client
        self._col = client[database or os.environ.get("MONGODB_DATABASE", "sentinel_ai")][collection]
        self._indexed = False
        self._index_lock = threading.Lock()

    def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        with self._index_lock:
            if self._indexed:
                return
            self._col.create_index("transaction_key")
            self._col.create_index("status")
            self._col.create_index("owner")
            self._col.create_index([("summary.priority_rank", -1), ("summary.risk_score", -1), ("created_at_utc", 1)])
            self._indexed = True

    @staticmethod
    def _record(doc: Optional[dict]) -> Optional[CaseRecord]:
        if not doc:
            return None
        doc.pop("_id", None)
        return CaseRecord.model_validate(doc)

    def close(self) -> None:
        self._client.close()

    def ping(self) -> bool:
        self._client.admin.command("ping")
        return True

    def create(self, record: CaseRecord) -> None:
        self._ensure_indexes()
        self._col.insert_one({"_id": record.case_id, **record.model_dump(mode="json")})

    def get(self, case_id: str) -> Optional[CaseRecord]:
        return self._record(self._col.find_one({"_id": case_id}))

    def find_active_by_transaction_key(self, key: str) -> Optional[CaseRecord]:
        doc = self._col.find_one({"transaction_key": key, "status": {"$ne": CaseStatus.INVESTIGATION_FAILED.value}},
                                 sort=[("created_at_utc", 1)])
        return self._record(doc)

    def update(self, case_id, fields, events=(), decision=None, require_status=None, require_fields=None):
        from pymongo import ReturnDocument

        flt: dict[str, Any] = {"_id": case_id}
        if require_status is not None:
            flt["status"] = {"$in": [s.value for s in require_status]}
        flt.update(require_fields or {})
        upd: dict[str, Any] = {"$set": {**{k: _dump(v) for k, v in fields.items()},
                                         "updated_at_utc": _now_json()}}
        push: dict[str, Any] = {}
        ev = [_dump(e) for e in events]
        if ev:
            push["audit_trail"] = {"$each": ev}
        if decision is not None:
            push["decisions"] = _dump(decision)
        if push:
            upd["$push"] = push
        return self._record(self._col.find_one_and_update(flt, upd, return_document=ReturnDocument.AFTER))

    def list(self, status=None, action=None, limit=50, offset=0, owner=None):
        self._ensure_indexes()
        flt: dict[str, Any] = {}
        if owner is not None:
            flt["owner"] = owner
        if status is not None:
            flt["status"] = status.value
        if action is not None:
            flt["summary.recommended_action"] = action
        proj = {k: 0 for k in ("investigation", "audit_trail", "decisions")}
        cur = (self._col.find(flt, proj)
               .sort([("summary.priority_rank", -1), ("summary.risk_score", -1), ("created_at_utc", 1)])
               .skip(offset).limit(limit))
        return [_list_view(d) for d in cur], self._col.count_documents(flt)

    def case_ids_with_status(self, statuses):
        cur = self._col.find({"status": {"$in": [s.value for s in statuses]}}, {"_id": 1}).sort("created_at_utc", 1)
        return [d["_id"] for d in cur]


def case_store_from_env() -> CaseStore:
    name = os.environ.get("SENTINEL_CASE_STORE", "json").strip().lower()
    if name == "json":
        return JsonCaseStore()
    if name == "mongodb":
        return MongoCaseStore()
    raise CaseStoreError(f"Unknown SENTINEL_CASE_STORE={name!r}; expected 'json' or 'mongodb'.")


__all__ = ["CaseStore", "CaseStoreError", "JsonCaseStore", "MongoCaseStore", "case_store_from_env"]
