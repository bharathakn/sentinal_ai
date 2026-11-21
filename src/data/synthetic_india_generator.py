"""
Sentinel AI — Custom Synthetic India Dataset Generator (v2.0.0)

Generates a relationally and behaviourally consistent synthetic investigation
world:

- Customers (1,200), accounts (1,500), devices (registered + created in-window),
  beneficiaries (established payees + payees added in-window)
- ~10,000 transactions with ground-truth targets in a SEPARATE file
- Graph edges for Neo4j (no label columns)

Why v2
------
v1 drew sender, receiver, device, location and per-transaction flags
independently at random. Scenario labels such as LAYERING or MULE existed only
as labels — the transactions had no chain / hub / burst structure — and the
entity tables contradicted the transaction flags (registered beneficiary pairs
matched 0.08% of transactions; distance flags disagreed with coordinates).
v2 generates each scenario as an actual pattern of transactions and derives
every behavioural feature from the generated ledger and entity tables.

Consistency guarantees (checked by validate_synthetic_dataset.py)
-----------------------------------------------------------------
* Every transaction (sender, receiver) pair has a beneficiary record added
  before the transaction; `is_new_beneficiary` = added < 30 days before the
  transaction; `time_since_beneficiary_added_min` is computed from that record.
* `is_new_device` = device first seen < 7 days before the transaction, or the
  device belongs to a different customer (shared device).
* `distance_from_home_km` = haversine(sender home, transaction coordinates);
  `tx_city` / `tx_state` name the actual transaction location.
* `tx_frequency_24h`, `time_since_last_tx_sec`, `amount_ratio_vs_30d_avg` and
  balances are computed from the chronologically ordered ledger.
* Transaction ids are assigned in chronological order.
* Ground-truth labels appear only in transactions_targets.csv.

100% synthetic; zero real PII; deterministic for a given seed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

GENERATOR_VERSION = "2.0.0"
IST = timezone(timedelta(hours=5, minutes=30))

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Shaurya", "Rohan", "Ananya", "Diya", "Sanya", "Priya", "Neha", "Pooja", "Aditi", "Kavya",
    "Rajesh", "Suresh", "Ramesh", "Sunil", "Anil", "Vikram", "Sanjay", "Deepak", "Amit", "Rahul",
    "Meera", "Sunita", "Anita", "Geeta", "Meena", "Seema", "Rekha", "Shoba", "Lata", "Usha",
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patel", "Mehta", "Shah", "Joshi", "Rao", "Nair", "Pillai",
    "Kumar", "Singh", "Das", "Mukherjee", "Banerjee", "Chatterjee", "Reddy", "Chowdhury", "Deshmukh", "Kulkarni",
    "Bhat", "Hegde", "Shetty", "Gowda", "Naidu", "Menon", "Kapoor", "Khanna", "Malhotra", "Saxena",
]

CITIES = [
    {"city": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "long": 72.8777},
    {"city": "Delhi", "state": "Delhi", "lat": 28.7041, "long": 77.1025},
    {"city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "long": 77.5946},
    {"city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "long": 78.4867},
    {"city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "long": 80.2707},
    {"city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "long": 88.3639},
    {"city": "Pune", "state": "Maharashtra", "lat": 18.5204, "long": 73.8567},
    {"city": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "long": 72.5714},
    {"city": "Jaipur", "state": "Rajasthan", "lat": 26.9124, "long": 75.7873},
    {"city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "long": 80.9462},
    {"city": "Patna", "state": "Bihar", "lat": 25.5941, "long": 85.1376},
    {"city": "Guwahati", "state": "Assam", "lat": 26.1445, "long": 91.7362},
    {"city": "Kochi", "state": "Kerala", "lat": 9.9312, "long": 76.2673},
    {"city": "Surat", "state": "Gujarat", "lat": 21.1702, "long": 72.8311},
    {"city": "Nagpur", "state": "Maharashtra", "lat": 21.1458, "long": 79.0882},
    {"city": "Indore", "state": "Madhya Pradesh", "lat": 22.7196, "long": 75.8577},
    {"city": "Bhopal", "state": "Madhya Pradesh", "lat": 23.2599, "long": 77.4126},
    {"city": "Visakhapatnam", "state": "Andhra Pradesh", "lat": 17.6868, "long": 83.2185},
    {"city": "Coimbatore", "state": "Tamil Nadu", "lat": 11.0168, "long": 76.9558},
    {"city": "Chandigarh", "state": "Chandigarh", "lat": 30.7333, "long": 76.7794},
    {"city": "Bhubaneswar", "state": "Odisha", "lat": 20.2961, "long": 85.8245},
    {"city": "Mysuru", "state": "Karnataka", "lat": 12.2958, "long": 76.6394},
]

BANK_IFSC_PREFIXES = ["SBIN000", "HDFC000", "ICIC000", "AXIS000", "PUNB000", "BOB000"]
UPI_HANDLES = ["@oksbi", "@okicici", "@paytm", "@ybl", "@axisbank", "@barodampay"]

UPI_MAX = 99_999.00
RTGS_MIN = 200_000.00
NEW_BENEFICIARY_DAYS = 30
NEW_DEVICE_DAYS = 7

# Transaction quotas per 10,000 (scaled for other sizes).
SCENARIO_QUOTAS = {
    "SCENARIO_1_NORMAL_LEGITIMATE": 8200,
    "SCENARIO_2_HIGH_VALUE_SPIKE": 200,
    "SCENARIO_3_RAPID_BURST": 150,
    "SCENARIO_4_NEW_BENEFICIARY_LARGE_TX": 150,
    "SCENARIO_5_NEW_DEVICE_SUSPICIOUS": 150,
    "SCENARIO_6_STRUCTURING_SPLITTING": 150,
    "SCENARIO_7_LAYERING_NETWORK": 200,
    "SCENARIO_8_MULE_PASS_THROUGH": 200,
    "SCENARIO_9_FRAUD_RING_HUB": 200,
    "SCENARIO_10_IMPOSSIBLE_TRAVEL": 150,
    "SCENARIO_11_SHARED_DEVICE_IP": 150,
    "SCENARIO_12_MIXED_BORDERLINE_TRAVEL": 100,
}
NORMAL = "SCENARIO_1_NORMAL_LEGITIMATE"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class _Tx:
    ts: datetime
    sender: str
    receiver: str
    amount: float
    channel: str
    device_id: str
    ip: str
    loc: Dict[str, Any]
    scenario: str
    is_fraud: int
    risk_label: str
    pattern_id: str
    extra: Dict[str, Any] = field(default_factory=dict)


class SyntheticIndiaDatasetGenerator:
    """Deterministic generator for the Custom Synthetic India Dataset (v2)."""

    def __init__(self, seed: int = 42, num_transactions: int = 10000,
                 num_customers: int = 1200, num_accounts: int = 1500):
        self.seed = seed
        self.num_transactions = num_transactions
        self.num_customers = num_customers
        self.num_accounts = num_accounts
        self.anchor_date = datetime(2026, 8, 1, 0, 0, 0, tzinfo=IST)
        self.end_date = self.anchor_date + timedelta(days=30)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_all(self) -> Dict[str, pd.DataFrame]:
        self.rnd = random.Random(self.seed)
        self.np_rng = np.random.default_rng(self.seed)

        self.customers = self._generate_customers()
        self.accounts = self._generate_accounts()
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.cust_devices: Dict[str, List[str]] = {}
        self._generate_devices()
        self.beneficiaries: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.payees: Dict[str, List[str]] = {}
        self._generate_established_beneficiaries()

        self.cust_accounts: Dict[str, List[str]] = {}
        for a in self.accounts.values():
            self.cust_accounts.setdefault(a["customer_id"], []).append(a["account_id"])
        self.account_ids = sorted(self.accounts)
        self.mule_pool = [a for a, v in self.accounts.items() if v["account_type"] == "MULE_SUSPECT"]
        # Criminal pool: mules, layering intermediaries, ring members and
        # structuring / burst beneficiaries come from a small set of accounts
        # (MULE_SUSPECT accounts plus ~6% of others). Victims (senders in
        # account-takeover style scenarios, mule sources) remain random
        # customers. Without this, almost every account would touch a fraud
        # pattern within one month, which is unrealistic.
        others = [a for a in self.account_ids if a not in set(self.mule_pool)]
        self.criminal_pool = sorted(self.mule_pool + self.rnd.sample(others, max(3, int(len(others) * 0.06))))

        txs = self._generate_transactions()
        features, targets, edges = self._finalise(txs)

        return {
            "customers": pd.DataFrame(list(self.customers.values())),
            "accounts": pd.DataFrame(list(self.accounts.values())),
            "devices": pd.DataFrame(self._device_rows(features)),
            "beneficiaries": pd.DataFrame(self._beneficiary_rows()),
            "transactions_features": pd.DataFrame(features),
            "transactions_targets": pd.DataFrame(targets),
            "graph_edges": pd.DataFrame(edges),
        }

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    def _generate_customers(self) -> Dict[str, Dict[str, Any]]:
        out = {}
        for i in range(1, self.num_customers + 1):
            cid = f"CUST_IND_{i:06d}"
            r = self.rnd.random()
            if r < 0.875:
                ctype, income = "INDIVIDUAL", float(self.np_rng.lognormal(12.5, 0.8))
            elif r < 0.958:
                ctype, income = "SOLE_PROPRIETORSHIP", float(self.np_rng.lognormal(14.0, 1.0))
            else:
                ctype, income = "CORPORATE", float(self.np_rng.lognormal(16.0, 1.2))
            loc = self.rnd.choice(CITIES)
            out[cid] = {
                "customer_id": cid,
                "customer_name_synthetic": f"{self.rnd.choice(FIRST_NAMES)} {self.rnd.choice(LAST_NAMES)}",
                "customer_type": ctype,
                "kyc_status": self.rnd.choices(["VERIFIED", "PENDING", "RE_KYC_DUE"], [0.92, 0.05, 0.03])[0],
                "pep_flag": 1 if self.rnd.random() < 0.012 else 0,
                "declared_annual_income_inr": round(income, 2),
                "home_city": loc["city"],
                "home_state": loc["state"],
                "home_lat": loc["lat"],
                "home_long": loc["long"],
                "customer_creation_date": (self.anchor_date - timedelta(days=self.rnd.randint(365, 1825))).strftime("%Y-%m-%d"),
            }
        return out

    def _generate_accounts(self) -> Dict[str, Dict[str, Any]]:
        out = {}
        cids = list(self.customers)
        for i in range(1, self.num_accounts + 1):
            aid = f"ACC_IND_{i:06d}"
            cid = cids[i - 1] if i <= len(cids) else self.rnd.choice(cids)
            ctype = self.customers[cid]["customer_type"]
            if ctype == "CORPORATE":
                atype = "CURRENT"
            elif ctype == "SOLE_PROPRIETORSHIP":
                atype = self.rnd.choice(["CURRENT", "SAVINGS"])
            else:
                atype = self.rnd.choices(["SAVINGS", "SALARY", "MULE_SUSPECT"], [0.85, 0.12, 0.03])[0]

            created = datetime.strptime(self.customers[cid]["customer_creation_date"], "%Y-%m-%d").replace(tzinfo=IST)
            if atype == "MULE_SUSPECT":
                opened = self.anchor_date - timedelta(days=self.rnd.randint(5, 60))  # young account
            else:
                opened = min(created + timedelta(days=self.rnd.randint(0, 180)),
                             self.anchor_date - timedelta(days=30))

            if atype == "CURRENT":
                bal = float(self.np_rng.lognormal(13.0, 1.0))
            elif atype == "MULE_SUSPECT":
                bal = self.rnd.uniform(500.0, 5000.0)
            else:
                bal = float(self.np_rng.lognormal(10.5, 1.0))
            out[aid] = {
                "account_id": aid,
                "customer_id": cid,
                "account_number_synthetic": f"SYN99{self.rnd.randint(1000000000, 9999999999)}",
                "ifsc_code_synthetic": f"{self.rnd.choice(BANK_IFSC_PREFIXES)}{self.rnd.randint(1000, 9999)}",
                "account_type": atype,
                "account_open_date": opened.strftime("%Y-%m-%d"),
                "account_age_days": max(1, (self.anchor_date - opened).days),
                "current_balance_inr": round(bal, 2),
                "historical_30d_avg_balance_inr": round(bal * self.rnd.uniform(0.8, 1.2), 2),
                "historical_30d_avg_tx_amt_inr": round(max(100.0, bal * self.rnd.uniform(0.05, 0.25)), 2),
                "historical_30d_tx_count": self.rnd.randint(5, 60),
            }
        return out

    def _add_device(self, cid: str, first_seen: datetime, registered: bool) -> str:
        did = f"DEV_IND_{len(self.devices) + 1:06d}"
        dtype = self.rnd.choices(["ANDROID_MOBILE", "IOS_MOBILE", "WEB_BROWSER"], [0.65, 0.25, 0.10])[0]
        self.devices[did] = {
            "device_id": did,
            "customer_id": cid,
            "device_fingerprint_synthetic": f"FPG_{self.rnd.getrandbits(64):016x}",
            "device_type": dtype,
            "os_version": {"ANDROID_MOBILE": "Android 13", "IOS_MOBILE": "iOS 17"}.get(dtype, "Chrome 122"),
            "app_version": f"v4.{self.rnd.randint(1, 9)}.{self.rnd.randint(0, 5)}",
            "first_seen": first_seen,
            "is_registered": 1 if registered else 0,
            "ip": f"103.{self.rnd.randint(1, 254)}.{self.rnd.randint(1, 254)}.{self.rnd.randint(1, 254)}",
        }
        self.cust_devices.setdefault(cid, []).append(did)
        return did

    def _generate_devices(self) -> None:
        for cid in self.customers:
            self._add_device(cid, self.anchor_date - timedelta(days=self.rnd.randint(30, 600)), True)
            if self.rnd.random() < 0.15:
                self._add_device(cid, self.anchor_date - timedelta(days=self.rnd.randint(30, 400)), True)

    def _add_beneficiary(self, sender: str, receiver: str, added: datetime, prior: int) -> None:
        key = (sender, receiver)
        if key in self.beneficiaries:
            # Patterns are generated in quota order, not time order: keep the
            # earliest addition so no transaction precedes its beneficiary.
            if added < self.beneficiaries[key]["added"]:
                self.beneficiaries[key]["added"] = added
            return
        self.beneficiaries[key] = {
            "sender_account_id": sender,
            "receiver_account_id": receiver,
            "receiver_vpa_synthetic": f"user{receiver.split('_')[-1]}{self.rnd.choice(UPI_HANDLES)}",
            "added": added,
            "beneficiary_status": "ACTIVE",
            "prior_tx_count": prior,
        }
        self.payees.setdefault(sender, []).append(receiver)

    def _generate_established_beneficiaries(self) -> None:
        ids = list(self.accounts)
        for aid in ids:
            for _ in range(self.rnd.randint(2, 5)):
                rcv = self.rnd.choice(ids)
                if rcv != aid:
                    self._add_beneficiary(aid, rcv, self.anchor_date - timedelta(days=self.rnd.randint(45, 400)),
                                          self.rnd.randint(1, 25))
        # established payees are the first entries of self.payees; remember them
        self.established = {k: list(v) for k, v in self.payees.items()}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _start_time(self, max_span_hours: float = 0.0) -> datetime:
        latest_day = max(0, 29 - int(math.ceil(max_span_hours / 24.0)))
        day = self.rnd.randint(0, latest_day)
        hour = self.rnd.randint(8, 21) if self.rnd.random() < 0.85 else self.rnd.choice([22, 23, 0, 1, 2, 3, 4, 5, 6, 7])
        return self.anchor_date + timedelta(days=day, hours=hour,
                                            minutes=self.rnd.randint(0, 59), seconds=self.rnd.randint(0, 59))

    def _home(self, aid: str) -> Dict[str, Any]:
        c = self.customers[self.accounts[aid]["customer_id"]]
        return {"city": c["home_city"], "state": c["home_state"],
                "lat": round(c["home_lat"] + self.rnd.uniform(-0.02, 0.02), 4),
                "long": round(c["home_long"] + self.rnd.uniform(-0.02, 0.02), 4)}

    def _travel(self, aid: str, lo: float, hi: float) -> Dict[str, Any]:
        c = self.customers[self.accounts[aid]["customer_id"]]
        dists = [(haversine_km(c["home_lat"], c["home_long"], x["lat"], x["long"]), x) for x in CITIES]
        inside = [x for d, x in dists if lo <= d <= hi]
        if inside:
            city = self.rnd.choice(inside)
        else:  # nearest available distance to the requested band
            city = min(dists, key=lambda t: min(abs(t[0] - lo), abs(t[0] - hi)))[1]
        return {"city": city["city"], "state": city["state"],
                "lat": round(city["lat"] + self.rnd.uniform(-0.02, 0.02), 4),
                "long": round(city["long"] + self.rnd.uniform(-0.02, 0.02), 4)}

    def _primary_device(self, aid: str) -> str:
        return self.cust_devices[self.accounts[aid]["customer_id"]][0]

    def _new_device(self, aid: str, ts: datetime, registered: bool) -> str:
        return self._add_device(self.accounts[aid]["customer_id"],
                                ts - timedelta(minutes=self.rnd.randint(0, 30)), registered)

    def _established_payee(self, aid: str) -> str:
        pool = self.established.get(aid)
        if not pool:
            rcv = self.rnd.choice([a for a in self.account_ids if a != aid][:50])
            self._add_beneficiary(aid, rcv, self.anchor_date - timedelta(days=60), 3)
            self.established.setdefault(aid, []).append(rcv)
            return rcv
        return self.rnd.choice(pool)

    def _new_payee(self, aid: str, ts: datetime, minutes: Tuple[int, int],
                   receiver: Optional[str] = None) -> str:
        if receiver is None:
            known = set(self.payees.get(aid, []))
            while True:
                receiver = self.rnd.choice(self.account_ids)
                if receiver != aid and receiver not in known:
                    break
        self._add_beneficiary(aid, receiver, ts - timedelta(minutes=self.rnd.randint(*minutes)), 0)
        return receiver

    def _normal_amount(self, aid: str) -> Tuple[float, str]:
        base = self.accounts[aid]["historical_30d_avg_tx_amt_inr"]
        amount = round(base * float(self.np_rng.lognormal(0.0, 0.6)), 2)
        channel = self.rnd.choices(["UPI", "NEFT", "RTGS"], [0.70, 0.22, 0.08])[0]
        if channel == "RTGS" and amount < RTGS_MIN:
            channel = "NEFT"
        if channel == "UPI" and amount > UPI_MAX:
            channel = "NEFT"
        return max(amount, 10.0), channel

    def _label(self, p_fraud: float) -> Tuple[int, str]:
        return (1, "FRAUDULENT") if self.rnd.random() < p_fraud else (0, "BORDERLINE")

    def _pick(self, exclude: set, pool: Optional[List[str]] = None) -> str:
        pool = pool or self.account_ids
        while True:
            a = self.rnd.choice(pool)
            if a not in exclude:
                return a

    # ------------------------------------------------------------------
    # Scenario patterns — each returns a list of _Tx
    # ------------------------------------------------------------------

    def _p_normal(self, pid: str) -> List[_Tx]:
        s = self.rnd.choice(self.account_ids)
        ts = self._start_time()
        if self.rnd.random() < 0.8:
            r = self._established_payee(s)
        else:
            r = self._new_payee(s, ts, (1440, 29 * 1440))
        amount, channel = self._normal_amount(s)
        dev = self._primary_device(s) if self.rnd.random() < 0.92 else self._new_device(s, ts, True)
        loc = self._home(s) if self.rnd.random() < 0.97 else self._travel(s, 100, 1500)
        return [_Tx(ts, s, r, amount, channel, dev, self.devices[dev]["ip"], loc, NORMAL, 0, "LEGITIMATE", pid)]

    def _p_high_value(self, pid: str) -> List[_Tx]:
        s = self.rnd.choice(self.account_ids)
        ts = self._start_time()
        amount = round(self.accounts[s]["historical_30d_avg_tx_amt_inr"] * self.rnd.uniform(8.0, 15.0), 2)
        channel = "RTGS" if amount >= RTGS_MIN else ("NEFT" if amount > UPI_MAX else "UPI")
        f, lbl = self._label(0.5)
        dev = self._primary_device(s)
        return [_Tx(ts, s, self._established_payee(s), amount, channel, dev, self.devices[dev]["ip"],
                    self._home(s), "SCENARIO_2_HIGH_VALUE_SPIKE", f, lbl, pid)]

    def _p_rapid_burst(self, pid: str) -> List[_Tx]:
        s = self.rnd.choice(self.account_ids)
        ts = self._start_time(2)
        f, lbl = self._label(0.67)
        dev = self._new_device(s, ts, False) if self.rnd.random() < 0.85 else self._primary_device(s)
        loc = self._home(s)
        out = []
        for _ in range(self.rnd.randint(5, 10)):
            ts = ts + timedelta(minutes=self.rnd.randint(2, 12))
            r = self._new_payee(s, ts, (2, 20), receiver=self._pick({s} | set(self.payees.get(s, [])), self.criminal_pool))
            out.append(_Tx(ts, s, r, round(self.rnd.uniform(2000, 8000), 2), "UPI", dev,
                           self.devices[dev]["ip"], loc, "SCENARIO_3_RAPID_BURST", f, lbl, pid))
        return out

    def _p_new_ben_large(self, pid: str) -> List[_Tx]:
        s = self.rnd.choice(self.account_ids)
        ts = self._start_time()
        f, lbl = self._label(0.67)
        dev = self._primary_device(s)
        payee = self._new_payee(s, ts, (2, 28), receiver=self._pick({s} | set(self.payees.get(s, [])), self.criminal_pool))
        return [_Tx(ts, s, payee, round(self.rnd.uniform(150000, 450000), 2),
                    "NEFT", dev, self.devices[dev]["ip"], self._home(s),
                    "SCENARIO_4_NEW_BENEFICIARY_LARGE_TX", f, lbl, pid)]

    def _p_new_device(self, pid: str) -> List[_Tx]:
        s = self.rnd.choice(self.account_ids)
        ts = self._start_time(1)
        f, lbl = self._label(0.67)
        dev = self._new_device(s, ts, False)
        loc = self._travel(s, 100, 500)
        out = []
        for _ in range(self.rnd.randint(1, 2)):
            ts = ts + timedelta(minutes=self.rnd.randint(1, 20))
            payee = self._new_payee(s, ts, (10, 60), receiver=self._pick({s} | set(self.payees.get(s, [])), self.criminal_pool))
            out.append(_Tx(ts, s, payee, round(self.rnd.uniform(40000, 95000), 2),
                           "UPI", dev, self.devices[dev]["ip"], loc, "SCENARIO_5_NEW_DEVICE_SUSPICIOUS", f, lbl, pid))
        return out

    def _p_structuring(self, pid: str) -> List[_Tx]:
        s = self.rnd.choice(self.criminal_pool)
        ts = self._start_time(20)
        dev = self._primary_device(s) if self.rnd.random() < 0.5 else self._new_device(s, ts, False)
        receivers = [self._new_payee(s, ts, (15, 120), receiver=self._pick({s} | set(self.payees.get(s, [])), self.criminal_pool))
                     for _ in range(self.rnd.randint(2, 4))]
        out = []
        for _ in range(self.rnd.randint(4, 6)):
            ts = ts + timedelta(minutes=self.rnd.randint(30, 240))
            amount = round(self.rnd.choice([self.rnd.uniform(45000, 49999), self.rnd.uniform(95000, 99999)]), 2)
            out.append(_Tx(ts, s, self.rnd.choice(receivers), amount, "UPI" if amount <= UPI_MAX else "NEFT",
                           dev, self.devices[dev]["ip"], self._home(s), "SCENARIO_6_STRUCTURING_SPLITTING",
                           1, "FRAUDULENT", pid))
        return out

    def _p_layering(self, pid: str) -> List[_Tx]:
        hops = self.rnd.randint(3, 5)
        chain = [self.rnd.choice(self.account_ids)]
        while len(chain) < hops + 1:
            chain.append(self._pick(set(chain), self.criminal_pool))
        ts = self._start_time(12)
        amount = round(self.rnd.uniform(300000, 1200000), 2)
        out = []
        for a, b in zip(chain, chain[1:]):
            ts = ts + timedelta(minutes=self.rnd.randint(10, 120))
            self._new_payee(a, ts, (5, 45), receiver=b)
            dev = self._primary_device(a)
            out.append(_Tx(ts, a, b, amount, "RTGS" if amount >= RTGS_MIN and self.rnd.random() < 0.5 else "NEFT",
                           dev, self.devices[dev]["ip"], self._home(a), "SCENARIO_7_LAYERING_NETWORK",
                           1, "FRAUDULENT", pid))
            amount = round(amount * self.rnd.uniform(0.97, 0.995), 2)
        return out

    def _p_mule(self, pid: str) -> List[_Tx]:
        mule = self.rnd.choice(self.mule_pool) if self.mule_pool else self.rnd.choice(self.account_ids)
        ts = self._start_time(12)
        out, total = [], 0.0
        sources = set()
        for _ in range(self.rnd.randint(3, 5)):
            src = self._pick(sources | {mule})
            sources.add(src)
            ts = ts + timedelta(minutes=self.rnd.randint(10, 90))
            amt = round(self.rnd.uniform(15000, 75000), 2)
            total += amt
            self._new_payee(src, ts, (10, 90), receiver=mule)
            dev = self._primary_device(src)
            out.append(_Tx(ts, src, mule, amt, "UPI", dev, self.devices[dev]["ip"], self._home(src),
                           "SCENARIO_8_MULE_PASS_THROUGH", 1, "FRAUDULENT", pid))
        remaining = round(total * self.rnd.uniform(0.85, 0.95), 2)
        dests = [self._pick(sources | {mule}, self.criminal_pool) for _ in range(self.rnd.randint(1, 2))]
        mdev = self._primary_device(mule)
        for i, d in enumerate(dests):
            ts = ts + timedelta(minutes=self.rnd.randint(10, 120))
            amt = remaining if i == len(dests) - 1 else round(remaining / len(dests), 2)
            remaining = round(remaining - amt, 2) if i < len(dests) - 1 else 0.0
            self._new_payee(mule, ts, (5, 60), receiver=d)
            out.append(_Tx(ts, mule, d, amt, "UPI" if amt <= UPI_MAX else "NEFT", mdev, self.devices[mdev]["ip"],
                           self._home(mule), "SCENARIO_8_MULE_PASS_THROUGH", 1, "FRAUDULENT", pid))
        return out

    def _p_ring(self, pid: str) -> List[_Tx]:
        n = self.rnd.randint(4, 6)
        members: List[str] = []
        while len(members) < n:
            members.append(self._pick(set(members), self.criminal_pool))
        hub = self._pick(set(members), self.criminal_pool)
        ts = self._start_time(48)
        out = []
        edges = list(zip(members, members[1:] + members[:1])) + [(m, hub) for m in members[: n - 1]]
        for a, b in edges:
            ts = ts + timedelta(minutes=self.rnd.randint(20, 300))
            self._new_payee(a, ts, (15, 180), receiver=b)  # keeps the earliest added date
            dev = self._primary_device(a)
            out.append(_Tx(ts, a, b, round(self.rnd.uniform(25000, 85000), 2), "UPI", dev,
                           self.devices[dev]["ip"], self._home(a), "SCENARIO_9_FRAUD_RING_HUB", 1, "FRAUDULENT", pid))
        return out

    def _p_impossible_travel(self, pid: str, with_home_tx: bool) -> List[_Tx]:
        s = self.rnd.choice(self.account_ids)
        ts = self._start_time(4)
        out = []
        if with_home_tx:
            amount, channel = self._normal_amount(s)
            dev = self._primary_device(s)
            out.append(_Tx(ts, s, self._established_payee(s), amount, channel, dev, self.devices[dev]["ip"],
                           self._home(s), NORMAL, 0, "LEGITIMATE", pid))
        ts = ts + timedelta(minutes=self.rnd.randint(30, 180))
        f, lbl = self._label(0.67)
        dev = self._new_device(s, ts, False) if self.rnd.random() < 0.88 else self._primary_device(s)
        out.append(_Tx(ts, s, self._established_payee(s), round(self.rnd.uniform(10000, 60000), 2), "UPI", dev,
                       self.devices[dev]["ip"], self._travel(s, 1200, 2500), "SCENARIO_10_IMPOSSIBLE_TRAVEL",
                       f, lbl, pid))
        return out

    def _p_shared_device(self, pid: str) -> List[_Tx]:
        owner = self.rnd.choice(self.criminal_pool)
        dev = self._primary_device(owner)
        ip = self.devices[dev]["ip"]
        owner_cust = self.accounts[owner]["customer_id"]
        ts = self._start_time(72)
        f, lbl = self._label(0.67)
        out, used = [], {owner}
        for _ in range(self.rnd.randint(3, 5)):
            s = self._pick(used, self.criminal_pool)
            if self.accounts[s]["customer_id"] == owner_cust:
                continue
            used.add(s)
            ts = ts + timedelta(minutes=self.rnd.randint(60, 900))
            r = self._new_payee(s, ts, (30, 300)) if self.rnd.random() < 0.85 else self._established_payee(s)
            out.append(_Tx(ts, s, r, round(self.rnd.uniform(15000, 50000), 2), "UPI", dev, ip,
                           self._home(owner), "SCENARIO_11_SHARED_DEVICE_IP", f, lbl, pid))
        return out

    def _p_borderline_travel(self, pid: str) -> List[_Tx]:
        s = self.rnd.choice(self.account_ids)
        ts = self._start_time()
        dev = self._new_device(s, ts, True) if self.rnd.random() < 0.4 else self._primary_device(s)
        amount = round(self.rnd.uniform(15000, 80000), 2)
        return [_Tx(ts, s, self._established_payee(s), amount, "UPI" if self.rnd.random() < 0.6 else "NEFT",
                    dev, self.devices[dev]["ip"], self._travel(s, 1500, 3500),
                    "SCENARIO_12_MIXED_BORDERLINE_TRAVEL", 0, "BORDERLINE", pid)]

    # ------------------------------------------------------------------

    def _generate_transactions(self) -> List[_Tx]:
        scale = self.num_transactions / 10000.0
        quotas = {k: max(1, int(round(v * scale))) for k, v in SCENARIO_QUOTAS.items()}
        quotas[NORMAL] = self.num_transactions - sum(v for k, v in quotas.items() if k != NORMAL)
        counts = {k: 0 for k in quotas}

        makers = {
            "SCENARIO_2_HIGH_VALUE_SPIKE": self._p_high_value,
            "SCENARIO_3_RAPID_BURST": self._p_rapid_burst,
            "SCENARIO_4_NEW_BENEFICIARY_LARGE_TX": self._p_new_ben_large,
            "SCENARIO_5_NEW_DEVICE_SUSPICIOUS": self._p_new_device,
            "SCENARIO_6_STRUCTURING_SPLITTING": self._p_structuring,
            "SCENARIO_7_LAYERING_NETWORK": self._p_layering,
            "SCENARIO_8_MULE_PASS_THROUGH": self._p_mule,
            "SCENARIO_9_FRAUD_RING_HUB": self._p_ring,
            "SCENARIO_11_SHARED_DEVICE_IP": self._p_shared_device,
            "SCENARIO_12_MIXED_BORDERLINE_TRAVEL": self._p_borderline_travel,
        }
        txs: List[_Tx] = []
        n_pattern = 0

        def take(batch: List[_Tx]) -> None:
            for t in batch:
                if counts[t.scenario] < quotas[t.scenario]:
                    counts[t.scenario] += 1
                    txs.append(t)

        for sc, maker in makers.items():
            while counts[sc] < quotas[sc]:
                n_pattern += 1
                take(maker(f"PAT_{n_pattern:05d}"))
        sc = "SCENARIO_10_IMPOSSIBLE_TRAVEL"
        while counts[sc] < quotas[sc]:
            n_pattern += 1
            take(self._p_impossible_travel(f"PAT_{n_pattern:05d}", counts[NORMAL] < quotas[NORMAL]))
        while counts[NORMAL] < quotas[NORMAL]:
            n_pattern += 1
            take(self._p_normal(f"PAT_{n_pattern:05d}"))
        return txs

    # ------------------------------------------------------------------
    # Derive features from the chronological ledger
    # ------------------------------------------------------------------

    def _finalise(self, txs: List[_Tx]):
        txs.sort(key=lambda t: (t.ts, t.sender, t.receiver))
        balances = {a: v["current_balance_inr"] for a, v in self.accounts.items()}
        last_debit: Dict[str, datetime] = {}
        recent_debits: Dict[str, List[datetime]] = {}
        last_credit: Dict[str, datetime] = {}
        features, targets, edges = [], [], []

        for i, t in enumerate(txs, start=1):
            tx_id = f"TXN_IND_202608_{i:06d}"
            acc = self.accounts[t.sender]
            sender_cust = acc["customer_id"]
            home = self.customers[sender_cust]

            prev = last_debit.get(t.sender)
            if prev is None:
                mean_gap = 30 * 86400 / max(1, acc["historical_30d_tx_count"])
                since_last = int(min(30 * 86400, max(60, self.np_rng.exponential(mean_gap))))
            else:
                since_last = int((t.ts - prev).total_seconds())
            window = [d for d in recent_debits.get(t.sender, []) if (t.ts - d) < timedelta(hours=24)]
            window.append(t.ts)
            recent_debits[t.sender] = window
            last_debit[t.sender] = t.ts

            ben = self.beneficiaries[(t.sender, t.receiver)]
            ben_min = int((t.ts - ben["added"]).total_seconds() // 60)
            dev = self.devices[t.device_id]
            new_dev = ((t.ts - dev["first_seen"]) < timedelta(days=NEW_DEVICE_DAYS)
                       or dev["customer_id"] != sender_cust)

            bal_before = balances[t.sender]
            if bal_before < t.amount:
                balances[t.sender] += t.amount + 50000.0
                bal_before = balances[t.sender]
            bal_after = round(bal_before - t.amount, 2)
            balances[t.sender] = bal_after
            balances[t.receiver] = round(balances[t.receiver] + t.amount, 2)

            lc = last_credit.get(t.sender)
            rapid_delta = int((t.ts - lc).total_seconds()) if lc and (t.ts - lc) < timedelta(hours=24) else 0
            last_credit[t.receiver] = t.ts

            features.append({
                "transaction_id": tx_id,
                "timestamp": t.ts.isoformat(),
                "day_of_month": t.ts.day,
                "hour_of_day": t.ts.hour,
                "day_of_week": t.ts.weekday(),
                "channel": t.channel,
                "transaction_type": "P2P" if t.channel == "UPI" else ("B2B" if t.channel == "RTGS" else "C2B"),
                "amount_inr": round(t.amount, 2),
                "status": "SUCCESS",
                "sender_account_id": t.sender,
                "receiver_account_id": t.receiver,
                "sender_customer_id": sender_cust,
                "receiver_customer_id": self.accounts[t.receiver]["customer_id"],
                "sender_vpa": f"user{t.sender.split('_')[-1]}@oksbi",
                "receiver_vpa": ben["receiver_vpa_synthetic"],
                "sender_ifsc": acc["ifsc_code_synthetic"],
                "receiver_ifsc": self.accounts[t.receiver]["ifsc_code_synthetic"],
                "device_id": t.device_id,
                "ip_address": t.ip,
                "tx_city": t.loc["city"],
                "tx_state": t.loc["state"],
                "tx_lat": t.loc["lat"],
                "tx_long": t.loc["long"],
                "distance_from_home_km": round(haversine_km(home["home_lat"], home["home_long"],
                                                            t.loc["lat"], t.loc["long"]), 2),
                "is_new_device": int(new_dev),
                "is_new_beneficiary": int(ben_min < NEW_BENEFICIARY_DAYS * 1440),
                "time_since_beneficiary_added_min": ben_min,
                "amount_ratio_vs_30d_avg": round(t.amount / max(1.0, acc["historical_30d_avg_tx_amt_inr"]), 4),
                "tx_frequency_24h": len(window),
                "time_since_last_tx_sec": since_last,
                "account_balance_before": round(bal_before, 2),
                "account_balance_after": bal_after,
            })
            targets.append({
                "transaction_id": tx_id,
                "alert_id": "" if t.scenario == NORMAL else f"ALT_IND_202608_{i:06d}",
                "is_fraud": t.is_fraud,
                "risk_label": t.risk_label,
                "is_flagged_alert": 0 if t.scenario == NORMAL else 1,
                "scenario_id": t.scenario,
                "pattern_id": t.pattern_id,
            })
            edges.append({
                ":START_ID": t.sender,
                ":END_ID": t.receiver,
                "transaction_id": tx_id,
                "amount_inr": round(t.amount, 2),
                "timestamp": t.ts.isoformat(),
                "channel": t.channel,
                "rapid_forward_delta_sec": rapid_delta,
                ":TYPE": "TRANSFERRED_TO",
            })
        self._final_txs = features
        return features, targets, edges

    def _device_rows(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        users: Dict[str, set] = {}
        for f in features:
            users.setdefault(f["device_id"], set()).add(f["sender_account_id"])
        rows = []
        for did, d in self.devices.items():
            own = set(self.cust_accounts.get(d["customer_id"], []))
            rows.append({
                "device_id": did,
                "customer_id": d["customer_id"],
                "device_fingerprint_synthetic": d["device_fingerprint_synthetic"],
                "device_type": d["device_type"],
                "os_version": d["os_version"],
                "app_version": d["app_version"],
                "first_seen_timestamp": d["first_seen"].isoformat(),
                "is_registered": d["is_registered"],
                "associated_accounts_count": len(own | users.get(did, set())),
            })
        return rows

    def _beneficiary_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for i, b in enumerate(sorted(self.beneficiaries.values(), key=lambda x: (x["added"], x["sender_account_id"])), 1):
            rows.append({
                "beneficiary_id": f"BEN_IND_{i:06d}",
                "sender_account_id": b["sender_account_id"],
                "receiver_account_id": b["receiver_account_id"],
                "receiver_vpa_synthetic": b["receiver_vpa_synthetic"],
                "beneficiary_added_timestamp": b["added"].isoformat(),
                "beneficiary_status": b["beneficiary_status"],
                "prior_tx_count": b["prior_tx_count"],
            })
        return rows
