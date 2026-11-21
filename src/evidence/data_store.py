"""
Sentinel AI — Evidence data store abstraction (Phase 9.5).

Evidence providers read entity data through an `EvidenceDataStore` instead of
importing fixture dictionaries directly. Two backends exist:

* ``fixture`` (default) — the hand-written Phase 5 fixtures in
  `fixture_data.py` (ACC001–ACC004). Used by unit tests.
* ``india_synthetic`` — the Custom Synthetic India Dataset in
  `dataset/processed/custom_india/` (1,500 accounts, 10,000 transactions).
  This makes Agent 2 evidence consistent with the Agent 3 graph and the
  Agent 1 India model, so one case can be investigated end to end.

Select with the environment variable ``SENTINEL_EVIDENCE_BACKEND`` or
`set_store()` (tests).

Point-in-time rule (india_synthetic)
------------------------------------
Transaction history, account statistics, known beneficiaries and linked
accounts are computed ONLY from transactions strictly before ``as_of`` (the
investigated transaction's timestamp). Evidence must never contain the
future, including the transaction under investigation.

Label firewall
--------------
The India store never reads `transactions_targets.csv`. Ground-truth labels
(is_fraud, risk_label, scenario_id) are not evidence.

All records remain SYNTHETIC and are labelled as such.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Protocol

from . import fixture_data as fx

SYNTHETIC_INDIA_NOTICE = (
    "SYNTHETIC — Custom Synthetic India Dataset (seed 42). Not real banking data; "
    "does not represent any real person, account or organisation."
)

_DEFAULT_INDIA_DIR = Path(__file__).resolve().parents[2] / "dataset" / "processed" / "custom_india"


class EvidenceDataStore(Protocol):
    """Read-only entity data used by the evidence providers."""

    backend_name: str
    source_prefix: str
    """Prefix for provider source names, e.g. 'MOCK' → 'MOCK_CORE_BANKING'."""
    synthetic_notice: str

    def get_account(self, account_id: str) -> Optional[dict[str, Any]]: ...
    def get_transaction_history(self, account_id: str,
                                as_of: Optional[datetime] = None) -> list[dict[str, Any]]: ...
    def get_account_stats(self, account_id: str,
                          as_of: Optional[datetime] = None) -> Optional[dict[str, Any]]: ...
    def get_device(self, device_id: str, as_of: Optional[datetime] = None) -> Optional[dict[str, Any]]: ...
    def is_device_registered_to_account(self, account_id: str, device_id: str) -> bool: ...
    def is_fraud_flagged(self, account_id: str) -> Optional[bool]:
        """True/False if a fraud-flag registry exists; None if unknown."""
    def reference_time(self, as_of: Optional[datetime] = None) -> datetime:
        """'Now' used for age calculations."""


# ---------------------------------------------------------------------------
# Fixture backend (Phase 5 behaviour, unchanged)
# ---------------------------------------------------------------------------

class FixtureStore:
    backend_name = "fixture"
    source_prefix = "MOCK"
    synthetic_notice = fx.SYNTHETIC_DATA_NOTICE

    _FRAUD_FLAGGED = {"ACC004"}
    _REFERENCE_TIME = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def get_account(self, account_id):
        return fx.get_account(account_id)

    def get_transaction_history(self, account_id, as_of=None):
        return fx.get_transaction_history(account_id)  # static fixture

    def get_account_stats(self, account_id, as_of=None):
        return fx.get_account_stats(account_id)

    def get_device(self, device_id, as_of=None):
        return fx.get_device(device_id)

    def is_device_registered_to_account(self, account_id, device_id):
        return fx.is_device_registered_to_account(account_id, device_id)

    def is_fraud_flagged(self, account_id):
        return account_id in self._FRAUD_FLAGGED

    def reference_time(self, as_of=None):
        return self._REFERENCE_TIME


# ---------------------------------------------------------------------------
# India synthetic backend
# ---------------------------------------------------------------------------

def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _income_band(income: Optional[float]) -> Optional[str]:
    if income is None:
        return None
    if income < 500_000:
        return "INR_BELOW_5L"
    if income < 1_000_000:
        return "INR_5L_10L"
    if income < 2_500_000:
        return "INR_10L_25L"
    return "INR_ABOVE_25L"


#: India dataset account_type values that are ground-truth labels.
LABEL_ACCOUNT_TYPES = frozenset({"MULE_SUSPECT"})


class IndiaSyntheticStore:
    backend_name = "india_synthetic"
    source_prefix = "SYNTHETIC_INDIA"
    synthetic_notice = SYNTHETIC_INDIA_NOTICE

    HISTORY_LIMIT = 50
    STATS_WINDOW_DAYS = 30

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._dir = Path(data_dir) if data_dir else _DEFAULT_INDIA_DIR
        self._lock = threading.Lock()
        self._loaded = False

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            import pandas as pd

            d = self._dir
            if not d.is_dir():
                raise FileNotFoundError(f"India synthetic dataset not found at {d}")
            customers = pd.read_csv(d / "customers.csv")
            accounts = pd.read_csv(d / "accounts.csv")
            devices = pd.read_csv(d / "devices.csv")
            beneficiaries = pd.read_csv(d / "beneficiaries.csv")
            beneficiaries["added_utc"] = pd.to_datetime(beneficiaries["beneficiary_added_timestamp"], utc=True)
            tx = pd.read_csv(d / "transactions_features.csv")  # NOT targets (label firewall)

            tx["ts_utc"] = pd.to_datetime(tx["timestamp"], utc=True)
            tx = tx.sort_values("ts_utc", kind="stable").reset_index(drop=True)

            self._customers = customers.set_index("customer_id").to_dict("index")
            self._accounts = accounts.set_index("account_id").to_dict("index")
            self._devices = devices.set_index("device_id").to_dict("index")
            self._tx = tx
            self._by_sender = {k: v for k, v in tx.groupby("sender_account_id").groups.items()}
            self._by_receiver = {k: v for k, v in tx.groupby("receiver_account_id").groups.items()}
            self._by_device = {k: v for k, v in tx.groupby("device_id").groups.items()}
            self._beneficiaries = {k: g for k, g in beneficiaries.groupby("sender_account_id")}
            self._dataset_end = tx["ts_utc"].max().to_pydatetime()
            self._loaded = True

    # ------------------------------------------------------------------
    def _rows_before(self, account_id: str, as_of: Optional[datetime]):
        """Transactions involving account strictly before as_of, oldest→newest."""
        import pandas as pd

        idx = list(self._by_sender.get(account_id, [])) + list(self._by_receiver.get(account_id, []))
        if not idx:
            return self._tx.iloc[0:0]
        rows = self._tx.loc[sorted(set(idx))]
        if as_of is not None:
            rows = rows[rows["ts_utc"] < pd.Timestamp(_to_utc(as_of))]
        return rows

    def get_account(self, account_id):
        self._load()
        acc = self._accounts.get(account_id)
        if acc is None:
            return None
        cust = self._customers.get(acc["customer_id"], {})
        opened = datetime.fromisoformat(str(acc["account_open_date"])).replace(tzinfo=timezone.utc)
        return {
            "account_id": account_id,
            "customer_id": acc["customer_id"],
            "customer_name": f"{cust.get('customer_name_synthetic')} (SYNTHETIC)" if cust else None,
            "kyc_status": cust.get("kyc_status", "UNKNOWN"),
            "pep": bool(cust.get("pep_flag")) if cust else None,
            # MULE_SUSPECT is the generator's ground-truth marker, not a bank
            # product type: masked (not replaced) so no agent can read it.
            "account_type": (None if acc.get("account_type") in LABEL_ACCOUNT_TYPES
                             else acc.get("account_type")),
            "bank_name": None,
            "ifsc_code": acc.get("ifsc_code_synthetic"),
            "account_opening_date": opened,
            "occupation": None,
            "income_band": _income_band(cust.get("declared_annual_income_inr")),
            "registered_city": cust.get("home_city"),
            "registered_state": cust.get("home_state"),
            "registered_country": "India",
            "registered_latitude": cust.get("home_lat"),
            "registered_longitude": cust.get("home_long"),
            "synthetic_notice": SYNTHETIC_INDIA_NOTICE,
        }

    def get_transaction_history(self, account_id, as_of=None):
        self._load()
        rows = self._rows_before(account_id, as_of).tail(self.HISTORY_LIMIT)
        out = []
        for r in rows.itertuples(index=False):
            debit = r.sender_account_id == account_id
            out.append({
                "tx_id": r.transaction_id,
                "counterparty_id": r.receiver_account_id if debit else r.sender_account_id,
                "amount_inr": Decimal(str(r.amount_inr)),
                "direction": "DEBIT" if debit else "CREDIT",
                "channel": r.channel,
                "timestamp": r.ts_utc.to_pydatetime(),
                "description": f"SYNTHETIC India dataset {r.transaction_type} transaction",
            })
        return out

    def get_account_stats(self, account_id, as_of=None):
        self._load()
        if account_id not in self._accounts:
            return None
        import pandas as pd

        prior = self._rows_before(account_id, as_of)
        end = pd.Timestamp(_to_utc(as_of)) if as_of is not None else pd.Timestamp(self._dataset_end)
        window = prior[prior["ts_utc"] >= end - pd.Timedelta(days=self.STATS_WINDOW_DAYS)]
        debits = window[window["sender_account_id"] == account_id]["amount_inr"]
        # Known = prior payees in the ledger plus registered beneficiaries that
        # were established (added at least 30 days before as_of).
        known = set(prior[prior["sender_account_id"] == account_id]["receiver_account_id"])
        ben = self._beneficiaries.get(account_id)
        if ben is not None:
            known |= set(ben[ben["added_utc"] <= end - pd.Timedelta(days=30)]["receiver_account_id"])
        known = sorted(known)
        n = len(window)
        return {
            "num_transactions_30d": int(n),
            "avg_debit_amount_inr": Decimal(str(round(float(debits.mean()), 2))) if len(debits) else Decimal("0"),
            "max_debit_30d_inr": Decimal(str(round(float(debits.max()), 2))) if len(debits) else Decimal("0"),
            "known_beneficiaries": known,
            "tx_frequency_per_week": round(n / self.STATS_WINDOW_DAYS * 7, 2),
            "computation_note": (
                f"Computed from India synthetic transactions strictly before "
                f"{end.isoformat()} ({self.STATS_WINDOW_DAYS}-day window for counts and "
                "debit amounts; known beneficiaries = all prior payees plus registered "
                "beneficiaries added at least 30 days earlier). "
                "Dataset covers 2026-08-01 to 2026-08-31 only, so history is short."
            ),
        }

    def get_device(self, device_id, as_of=None):
        self._load()
        dev = self._devices.get(device_id)
        if dev is None:
            return None
        import pandas as pd

        # Owner's accounts plus any account that transacted from this device
        # strictly before as_of (point-in-time; reveals shared devices).
        accounts = {a for a, v in self._accounts.items() if v["customer_id"] == dev["customer_id"]}
        used = self._tx.loc[list(self._by_device.get(device_id, []))]
        if as_of is not None:
            used = used[used["ts_utc"] < pd.Timestamp(_to_utc(as_of))]
        accounts = sorted(accounts | set(used["sender_account_id"]))
        first_seen = dev.get("first_seen_timestamp")
        return {
            "device_id": device_id,
            "device_fingerprint": dev.get("device_fingerprint_synthetic"),
            "device_type": dev.get("device_type"),
            "device_info": f"{dev.get('os_version')} / app {dev.get('app_version')} (SYNTHETIC)",
            "associated_accounts": accounts,
            "first_seen": datetime.fromisoformat(first_seen) if isinstance(first_seen, str) else None,
            "registration_status": "REGISTERED" if int(dev.get("is_registered", 0)) == 1 else "NOT_REGISTERED",
            "num_associated_accounts": len(accounts),
            "customer_id": dev["customer_id"],
            "synthetic_notice": SYNTHETIC_INDIA_NOTICE,
        }

    def is_device_registered_to_account(self, account_id, device_id):
        self._load()
        dev = self._devices.get(device_id)
        acc = self._accounts.get(account_id)
        if dev is None or acc is None:
            return False
        return int(dev.get("is_registered", 0)) == 1 and dev["customer_id"] == acc["customer_id"]

    def is_fraud_flagged(self, account_id):
        return None  # the India dataset has no fraud-flag registry

    def reference_time(self, as_of=None):
        self._load()
        return _to_utc(as_of) if as_of is not None else self._dataset_end


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

_BACKENDS = {"fixture": FixtureStore, "india_synthetic": IndiaSyntheticStore}
_store: Optional[EvidenceDataStore] = None
_store_lock = threading.Lock()


def get_store() -> EvidenceDataStore:
    """Return the active store (created from SENTINEL_EVIDENCE_BACKEND on first use)."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                name = os.environ.get("SENTINEL_EVIDENCE_BACKEND", "fixture").strip().lower()
                if name not in _BACKENDS:
                    raise ValueError(
                        f"Unknown SENTINEL_EVIDENCE_BACKEND={name!r}; "
                        f"expected one of {sorted(_BACKENDS)}"
                    )
                _store = _BACKENDS[name]()
    return _store


def set_store(store: Optional[EvidenceDataStore]) -> None:
    """Install a store (None resets to env-based selection on next get_store())."""
    global _store
    with _store_lock:
        _store = store
