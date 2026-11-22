"""
Sentinel AI — store for dataset runs and their append-only event log.

Uses the same backend as the case store: JSON files (``SENTINEL_RUN_DIR``,
default next to the cases) or MongoDB (collections ``runs`` / ``run_events``).
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

from .case_store import CaseStore

_RUN_ID = re.compile(r"RUN-[A-F0-9]{12}")


class RunStore(Protocol):
    def create(self, run: dict) -> None: ...
    def get(self, run_id: str) -> Optional[dict]: ...
    def update(self, run_id: str, fields: dict[str, Any]) -> None: ...
    def list(self, limit: int = 20) -> list[dict]: ...
    def ids_with_status(self, statuses: Iterable[str]) -> list[str]: ...
    def append_event(self, run_id: str, event: dict) -> None: ...
    def events(self, run_id: str, after: int = 0, limit: int = 500) -> list[dict]: ...


class JsonRunStore:
    def __init__(self, directory: os.PathLike | str) -> None:
        self._dir = Path(directory)
        self._lock = threading.RLock()

    def _path(self, run_id: str, suffix: str) -> Optional[Path]:
        return self._dir / f"{run_id}{suffix}" if _RUN_ID.fullmatch(run_id) else None

    def _write(self, run: dict) -> None:
        path = self._path(run["run_id"], ".json")
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(run))
        os.replace(tmp, path)

    def create(self, run):
        with self._lock:
            self._write(run)

    def get(self, run_id):
        path = self._path(run_id, ".json")
        if path is None or not path.is_file():
            return None
        return json.loads(path.read_text())

    def update(self, run_id, fields):
        with self._lock:
            run = self.get(run_id)
            if run is not None:
                run.update(fields)
                self._write(run)

    def _all(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in self._dir.glob("RUN-*.json")]

    def list(self, limit=20):
        return sorted(self._all(), key=lambda r: r["created_at_utc"], reverse=True)[:limit]

    def ids_with_status(self, statuses):
        wanted = set(statuses)
        return [r["run_id"] for r in self._all() if r["status"] in wanted]

    def append_event(self, run_id, event):
        path = self._path(run_id, ".events.jsonl")
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                fh.write(json.dumps(event) + "\n")

    def events(self, run_id, after=0, limit=500):
        path = self._path(run_id, ".events.jsonl")
        if path is None or not path.is_file():
            return []
        with self._lock:
            lines = path.read_text().splitlines()
        return [e for e in map(json.loads, lines) if e["seq"] > after][:limit]


class MongoRunStore:
    def __init__(self, database: Any) -> None:
        self._runs, self._events = database["runs"], database["run_events"]
        self._indexed = False

    def _ensure_indexes(self) -> None:
        if not self._indexed:
            self._runs.create_index([("created_at_utc", -1)])
            self._events.create_index([("run_id", 1), ("seq", 1)], unique=True)
            self._indexed = True

    def create(self, run):
        self._ensure_indexes()
        self._runs.insert_one({"_id": run["run_id"], **run})

    def get(self, run_id):
        return self._runs.find_one({"_id": run_id}, {"_id": 0})

    def update(self, run_id, fields):
        self._runs.update_one({"_id": run_id}, {"$set": fields})

    def list(self, limit=20):
        return list(self._runs.find({}, {"_id": 0}).sort("created_at_utc", -1).limit(limit))

    def ids_with_status(self, statuses):
        return [d["_id"] for d in self._runs.find({"status": {"$in": list(statuses)}}, {"_id": 1})]

    def append_event(self, run_id, event):
        self._events.insert_one({"run_id": run_id, **event})

    def events(self, run_id, after=0, limit=500):
        return list(self._events.find({"run_id": run_id, "seq": {"$gt": after}}, {"_id": 0, "run_id": 0})
                    .sort("seq", 1).limit(limit))


def run_store_for(case_store: CaseStore) -> RunStore:
    """A run store on the same backend (and database) as the case store."""
    if case_store.backend_name == "mongodb":
        return MongoRunStore(case_store._col.database)
    directory = os.environ.get("SENTINEL_RUN_DIR") or case_store._dir.parent / "runs"
    return JsonRunStore(directory)


__all__ = ["RunStore", "JsonRunStore", "MongoRunStore", "run_store_for"]
