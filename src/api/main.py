"""
Sentinel AI — API server entry point.

    uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --workers 1

Loads ``.env`` when present (local development; values already set in the
environment, e.g. on Render, take precedence) and defaults the evidence backend
to the synthetic India dataset, as the investigation scripts do.
Run exactly one worker: investigations run on one in-process worker thread.
"""

from __future__ import annotations

import logging
import os

try:
    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
except ImportError:  # pragma: no cover
    pass

os.environ.setdefault("SENTINEL_EVIDENCE_BACKEND", "india_synthetic")
logging.basicConfig(level=os.environ.get("SENTINEL_LOG_LEVEL", "INFO"))

from .app import create_app  # noqa: E402

app = create_app()
