"""
Sentinel AI — limits that make public sign-up safe on a 512 MB server.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

from fastapi import HTTPException

MAX_BODY_BYTES = 128 * 1024  # every request body except a dataset upload (which has its own cap)


class AllowanceUsed(Exception):
    """A self-registered account used its daily allowance (message is safe to show)."""


class DailyAllowance:
    """Investigations per self-registered account in 24 hours. Team accounts have no limit."""

    def __init__(self, limit: Optional[int] = None) -> None:
        self.limit = limit if limit is not None else int(os.environ.get("SENTINEL_USER_RUNS_PER_DAY", "30"))
        self._used: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, workspace: Optional[str]) -> None:
        if workspace is None:
            return
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._used.get(workspace, []) if now - t < 86400]
            if len(recent) >= self.limit:
                raise AllowanceUsed(f"You have used today's {self.limit} investigations. Try again tomorrow.")
            if recent:
                self._used[workspace] = recent
            else:
                self._used.pop(workspace, None)

    def spend(self, workspace: Optional[str]) -> None:
        if workspace is None:
            return
        with self._lock:
            self._used.setdefault(workspace, []).append(time.monotonic())


class BodyLimit:
    """ASGI middleware: refuse large bodies before they are buffered, signed in or not."""

    def __init__(self, app, exempt: str = "/api/v1/runs/upload", limit: int = MAX_BODY_BYTES) -> None:
        self.app, self.exempt, self.limit = app, exempt, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == self.exempt:
            return await self.app(scope, receive, send)
        seen = 0

        async def limited():
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > self.limit:
                raise HTTPException(status_code=413, detail="The request is too large.")
            return message

        await self.app(scope, limited, send)
