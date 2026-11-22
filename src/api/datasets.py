"""
Sentinel AI — datasets for live investigation runs: the demo and uploads.

Uploads use the column layout of the India demo dataset. Parsing is an
allow-list: unknown columns, label columns included, are dropped, and so are
the free-text place names (tx_city / tx_state). Every string that can reach an
agent or the LLM is an identifier or code in a narrow, space-free format.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional

from ..schemas.adapters.india_adapter import IndiaSyntheticAdapter
from ..schemas.canonical_transaction import CanonicalTransaction, DataSource

DEMO_DIR = Path(__file__).resolve().parents[2] / "dataset/processed/custom_india"
DEMO_NAME = "India synthetic transactions"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_ROWS = 10_000
MAX_REPORTED_ERRORS = 8

# The account-history columns are required, not optional: Agent 1's model treats
# their absence as suspicious. Without amount_ratio_vs_30d_avg alone it flags
# about 73% of legitimate transactions (about 6% with it; measured on unseen
# synthetic data, 2026-11-22). The bank-side average cannot be derived from the file.
HISTORY = ("amount_ratio_vs_30d_avg", "tx_frequency_24h", "time_since_last_tx_sec")
REQUIRED = ("transaction_id", "timestamp", "amount_inr", "channel", "sender_account_id",
            "receiver_account_id") + HISTORY
YEARS = range(1990, 2101)  # outside this, the agents' look-back windows can overflow
_ID = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
_CODE = re.compile(r"[A-Za-z0-9_.@:\-]{1,80}")
_ID_COLUMNS = ("transaction_id", "sender_account_id", "receiver_account_id", "sender_customer_id",
               "receiver_customer_id", "device_id")
_CODE_COLUMNS = ("channel", "transaction_type", "status", "sender_vpa", "receiver_vpa", "sender_ifsc",
                 "receiver_ifsc", "ip_address")
_FLOAT_COLUMNS = ("amount_inr", "tx_lat", "tx_long", "distance_from_home_km", "amount_ratio_vs_30d_avg",
                  "account_balance_before", "account_balance_after")
_INT_COLUMNS = ("day_of_month", "hour_of_day", "day_of_week", "time_since_beneficiary_added_min",
                "tx_frequency_24h", "time_since_last_tx_sec")
_BOOL_COLUMNS = ("is_new_device", "is_new_beneficiary")
COLUMNS = _ID_COLUMNS + _CODE_COLUMNS + _FLOAT_COLUMNS + _INT_COLUMNS + _BOOL_COLUMNS + ("timestamp",)
_BOOL = {"1": 1, "1.0": 1, "true": 1, "0": 0, "0.0": 0, "false": 0}


class DatasetError(ValueError):
    """The file cannot be used; the message is safe to show to the analyst."""


@dataclass
class Dataset:
    kind: str  # DEMO | UPLOAD
    name: str
    rows: list[dict[str, Any]]
    rejected: int = 0
    errors: list[str] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)

    def info(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "rows": len(self.rows), "rejected_rows": self.rejected,
                "row_errors": self.errors, "ignored_columns": self.ignored_columns}

    def transaction(self, row: dict[str, Any]) -> CanonicalTransaction:
        tx = IndiaSyntheticAdapter.from_row(row)
        if self.kind == "UPLOAD":
            tx = tx.model_copy(update={"source_dataset": DataSource.UPLOADED_DATASET.value})
        return tx

    def transactions(self) -> Iterator[CanonicalTransaction]:
        return (self.transaction(r) for r in self.rows)


def load_demo() -> Dataset:
    path = DEMO_DIR / "transactions_features.csv"  # never the targets file (label firewall)
    if not path.is_file():
        raise DatasetError("The demo dataset is not built on this server.")
    import pandas as pd

    return Dataset("DEMO", DEMO_NAME, pd.read_csv(path).to_dict("records"))


@lru_cache(maxsize=1)
def demo_info() -> dict[str, Any]:
    rows = load_demo().rows
    times = [str(r["timestamp"]) for r in rows]
    return {"name": DEMO_NAME, "rows": len(rows),
            "accounts": len({r["sender_account_id"] for r in rows} | {r["receiver_account_id"] for r in rows}),
            "first_date": min(times)[:10], "last_date": max(times)[:10],
            "channels": sorted(Counter(str(r["channel"]) for r in rows)),
            "total_amount_inr": round(sum(float(r["amount_inr"]) for r in rows), 2)}


def sample_csv(n: int = 500) -> str:
    """The first ``n`` demo rows, as an example of the upload layout (no labels)."""
    with (DEMO_DIR / "transactions_features.csv").open(encoding="utf-8") as fh:
        return "".join(line for _, line in zip(range(n + 1), fh))


def _clean(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in COLUMNS:
        value = raw.get(col)
        text = "" if value is None else str(value).strip()
        if text == "" or text.lower() in ("nan", "null", "none"):
            if col in REQUIRED:
                raise ValueError(f"{col} is empty")
            out[col] = None
        elif col in _FLOAT_COLUMNS or col in _INT_COLUMNS:
            try:
                number = float(text)
            except ValueError:
                raise ValueError(f"{col} is not a number") from None
            if not math.isfinite(number) or abs(number) > 1e13:
                raise ValueError(f"{col} is out of range")
            if col in ("amount_inr", "amount_ratio_vs_30d_avg") and number <= 0:
                raise ValueError(f"{col} must be above zero")
            if col in HISTORY and number < 0:
                raise ValueError(f"{col} must not be negative")
            out[col] = int(number) if col in _INT_COLUMNS else number
        elif col in _BOOL_COLUMNS:
            if text.lower() not in _BOOL:
                raise ValueError(f"{col} must be 0/1 or true/false")
            out[col] = _BOOL[text.lower()]
        elif col == "timestamp":
            try:
                year = datetime.fromisoformat(text).year
            except ValueError:
                raise ValueError("timestamp must be ISO 8601, e.g. 2026-08-03T20:12:29+05:30") from None
            if year not in YEARS:
                raise ValueError(f"timestamp year must be {YEARS.start} to {YEARS.stop - 1}")
            out[col] = text
        else:
            pattern = _ID if col in _ID_COLUMNS else _CODE
            if not pattern.fullmatch(text):
                raise ValueError(f"{col} has unsupported characters or is too long")
            out[col] = text
    return out


def safe_name(filename: Optional[str]) -> str:
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^\w .()\-]", "_", base)[:80].strip() or "Uploaded dataset"


def parse_upload(content: bytes, filename: Optional[str]) -> Dataset:
    if len(content) > MAX_UPLOAD_BYTES:
        raise DatasetError(f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DatasetError("The file must be UTF-8 CSV or JSON. Save Excel files as CSV first.") from None
    try:
        if text.lstrip()[:1] in ("[", "{"):
            data = json.loads(text)
            records = data.get("transactions") if isinstance(data, dict) else data
            if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
                raise DatasetError('JSON must be a list of transactions or {"transactions": [...]}.')
            columns = {str(k) for r in records for k in r}
        else:
            reader = csv.DictReader(io.StringIO(text))
            records = []
            for record in reader:
                records.append(record)
                if len(records) > MAX_UPLOAD_ROWS:
                    break
            columns = {c for c in reader.fieldnames or [] if c}
    except (csv.Error, json.JSONDecodeError, RecursionError):
        raise DatasetError("The file could not be read as CSV or JSON.") from None
    if not records:
        raise DatasetError("The file has no transactions.")
    if len(records) > MAX_UPLOAD_ROWS:
        raise DatasetError(f"The file has more than {MAX_UPLOAD_ROWS:,} transactions.")
    missing = [c for c in REQUIRED if c not in columns]
    if missing:
        raise DatasetError("Missing required columns: " + ", ".join(missing)
                           + ". Download the sample file to see the layout the models need.")

    ds = Dataset("UPLOAD", safe_name(filename), [], ignored_columns=sorted(c[:64] for c in columns - set(COLUMNS))[:30])
    seen: set[str] = set()
    for number, raw in enumerate(records, start=1):
        try:
            row = _clean(raw)
            if row["transaction_id"] in seen:
                raise ValueError("transaction_id is repeated")
            ds.transaction(row)  # must satisfy the canonical schema
            seen.add(row["transaction_id"])
            ds.rows.append(row)
        except Exception as exc:  # noqa: BLE001 — one bad row never fails the file
            ds.rejected += 1
            if len(ds.errors) < MAX_REPORTED_ERRORS:
                reason = str(exc) if type(exc) is ValueError else "does not fit the transaction schema"
                ds.errors.append(f"Row {number}: {reason}")
    if not ds.rows:
        raise DatasetError("No row could be used. " + "; ".join(ds.errors[:3]))
    return ds
