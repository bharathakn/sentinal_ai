"""
Sentinel AI — Phase 5: Centralised Synthetic Evidence Fixtures.

This module is the SINGLE SOURCE OF TRUTH for all synthetic (mock) evidence data
used by the seven evidence providers.

Rules
-----
* All six mock providers (Core Banking, KYC, Device Registry, Beneficiary,
  Sanctions, Geolocation) MUST read from this module.
* Never hardcode conflicting account profiles independently in provider modules.
* Synthetic data is clearly labelled as SYNTHETIC in every record.
* Never use real personal data, actual PAN numbers, or real sanctions subjects.
* Repeated calls with the same identifiers must produce identical business data.
* Only request metadata (timestamps, request_id) may vary between calls.

Scenario identifiers
--------------------
ACC001 : Sender in normal and suspicious transactions.
ACC002 : Beneficiary in normal transaction (established, known account).
ACC003 : Beneficiary in suspicious transaction (new, recently created).
ACC004 : High-risk account (known fraud flag in history).
DEV001 : Known device registered to ACC001.
DEV002 : New device (not previously registered to any account).
DEV003 : Shared device associated with multiple accounts (risk signal).
SANC001: Synthetic sanctions-matched subject name.
SANC002: Non-matched subject name.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Sentinel: mark all synthetic data clearly
# ---------------------------------------------------------------------------

SYNTHETIC_DATA_NOTICE = (
    "SYNTHETIC — This record is entirely fabricated for prototype testing. "
    "It does not represent any real person, account, or organisation."
)

# ---------------------------------------------------------------------------
# Fixed reference timestamps (deterministic)
# ---------------------------------------------------------------------------

_BASE_TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
_OLDER_TS = datetime(2022, 3, 10, 8, 30, 0, tzinfo=timezone.utc)
_RECENT_TS = datetime(2024, 1, 10, 14, 0, 0, tzinfo=timezone.utc)
_NEW_TS = datetime(2024, 1, 14, 23, 50, 0, tzinfo=timezone.utc)  # Very recent


# ---------------------------------------------------------------------------
# Account profiles
# ---------------------------------------------------------------------------

ACCOUNTS: dict[str, dict[str, Any]] = {
    "ACC001": {
        "account_id": "ACC001",
        "customer_id": "CUST001",
        "customer_name": "Arjun Sharma (SYNTHETIC)",
        "email": "arjun.sharma.synthetic@example.com",
        "email_domain": "example.com",
        "phone": "+91-99999-00001",
        "kyc_status": "VERIFIED",
        "pep": False,
        "account_type": "SAVINGS",
        "bank_name": "Synthetic National Bank",
        "ifsc_code": "SYNB0001234",
        "account_opening_date": datetime(2020, 6, 1, tzinfo=timezone.utc),
        "occupation": "Software Engineer",
        "income_band": "INR_10L_25L",        # declared annual income band
        "registered_city": "Bengaluru",
        "registered_state": "Karnataka",
        "registered_country": "India",
        "registered_latitude": 12.9716,
        "registered_longitude": 77.5946,
        "registered_zip": "560001",
        "synthetic_notice": SYNTHETIC_DATA_NOTICE,
    },
    "ACC002": {
        "account_id": "ACC002",
        "customer_id": "CUST002",
        "customer_name": "Priya Menon (SYNTHETIC)",
        "email": "priya.menon.synthetic@example.com",
        "email_domain": "example.com",
        "phone": "+91-99999-00002",
        "kyc_status": "VERIFIED",
        "pep": False,
        "account_type": "SAVINGS",
        "bank_name": "Synthetic National Bank",
        "ifsc_code": "SYNB0005678",
        "account_opening_date": datetime(2019, 4, 15, tzinfo=timezone.utc),
        "occupation": "Teacher",
        "income_band": "INR_5L_10L",
        "registered_city": "Bengaluru",
        "registered_state": "Karnataka",
        "registered_country": "India",
        "registered_latitude": 12.9352,
        "registered_longitude": 77.6245,
        "registered_zip": "560034",
        "synthetic_notice": SYNTHETIC_DATA_NOTICE,
    },
    "ACC003": {
        "account_id": "ACC003",
        "customer_id": "CUST003",
        "customer_name": "New User (SYNTHETIC)",
        "email": "newuser.synthetic@anon.example.com",
        "email_domain": "anon.example.com",
        "phone": "+91-99999-00003",
        "kyc_status": "PENDING",            # Not yet fully verified
        "pep": False,
        "account_type": "SAVINGS",
        "bank_name": "Synthetic Challenger Bank",
        "ifsc_code": "SYNCH0000001",
        "account_opening_date": datetime(2024, 1, 13, tzinfo=timezone.utc),  # 2 days old
        "occupation": "UNKNOWN",
        "income_band": "UNKNOWN",
        "registered_city": "Mumbai",
        "registered_state": "Maharashtra",
        "registered_country": "India",
        "registered_latitude": 19.0760,
        "registered_longitude": 72.8777,
        "registered_zip": "400001",
        "synthetic_notice": SYNTHETIC_DATA_NOTICE,
    },
    "ACC004": {
        "account_id": "ACC004",
        "customer_id": "CUST004",
        "customer_name": "Risk Subject (SYNTHETIC)",
        "email": "risksubject.synthetic@example.com",
        "email_domain": "example.com",
        "phone": "+91-99999-00004",
        "kyc_status": "FLAGGED",
        "pep": True,
        "account_type": "CURRENT",
        "bank_name": "Synthetic National Bank",
        "ifsc_code": "SYNB0009999",
        "account_opening_date": datetime(2021, 9, 1, tzinfo=timezone.utc),
        "occupation": "Business",
        "income_band": "INR_ABOVE_50L",
        "registered_city": "Delhi",
        "registered_state": "Delhi",
        "registered_country": "India",
        "registered_latitude": 28.6139,
        "registered_longitude": 77.2090,
        "registered_zip": "110001",
        "synthetic_notice": SYNTHETIC_DATA_NOTICE,
    },
}


# ---------------------------------------------------------------------------
# Transaction history per account
# ---------------------------------------------------------------------------

# Each entry: {tx_id, counterparty_id, amount_inr, direction, timestamp, channel}
TRANSACTION_HISTORY: dict[str, list[dict[str, Any]]] = {
    "ACC001": [
        {
            "tx_id": "TX-ACC001-001",
            "counterparty_id": "ACC002",
            "amount_inr": Decimal("5000.00"),
            "direction": "DEBIT",
            "channel": "UPI",
            "timestamp": datetime(2024, 1, 5, 10, 30, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC regular transfer to ACC002",
        },
        {
            "tx_id": "TX-ACC001-002",
            "counterparty_id": "ACC002",
            "amount_inr": Decimal("3200.00"),
            "direction": "DEBIT",
            "channel": "UPI",
            "timestamp": datetime(2024, 1, 8, 14, 15, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC regular transfer to ACC002",
        },
        {
            "tx_id": "TX-ACC001-003",
            "counterparty_id": "MERCHANT001",
            "amount_inr": Decimal("1500.00"),
            "direction": "DEBIT",
            "channel": "CARD",
            "timestamp": datetime(2024, 1, 10, 9, 0, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC merchant payment",
        },
        {
            "tx_id": "TX-ACC001-004",
            "counterparty_id": "SALARY",
            "amount_inr": Decimal("85000.00"),
            "direction": "CREDIT",
            "channel": "NEFT",
            "timestamp": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC salary credit",
        },
        {
            "tx_id": "TX-ACC001-005",
            "counterparty_id": "ACC003",
            "amount_inr": Decimal("95000.00"),    # Suspicious: large to new account
            "direction": "DEBIT",
            "channel": "NEFT",
            "timestamp": datetime(2024, 1, 15, 9, 55, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC high-value transfer to new account (suspicious scenario)",
        },
    ],
    "ACC002": [
        {
            "tx_id": "TX-ACC002-001",
            "counterparty_id": "ACC001",
            "amount_inr": Decimal("5000.00"),
            "direction": "CREDIT",
            "channel": "UPI",
            "timestamp": datetime(2024, 1, 5, 10, 30, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC received from ACC001",
        },
        {
            "tx_id": "TX-ACC002-002",
            "counterparty_id": "ACC001",
            "amount_inr": Decimal("3200.00"),
            "direction": "CREDIT",
            "channel": "UPI",
            "timestamp": datetime(2024, 1, 8, 14, 15, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC received from ACC001",
        },
    ],
    "ACC003": [
        {
            "tx_id": "TX-ACC003-001",
            "counterparty_id": "ACC001",
            "amount_inr": Decimal("95000.00"),
            "direction": "CREDIT",
            "channel": "NEFT",
            "timestamp": datetime(2024, 1, 15, 9, 55, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC received from ACC001 (suspicious scenario)",
        },
    ],
    "ACC004": [
        {
            "tx_id": "TX-ACC004-001",
            "counterparty_id": "UNKNOWN",
            "amount_inr": Decimal("500000.00"),
            "direction": "DEBIT",
            "channel": "WIRE",
            "timestamp": datetime(2023, 11, 20, 3, 0, 0, tzinfo=timezone.utc),
            "description": "SYNTHETIC large offshore wire — risk scenario",
        },
    ],
}

# Pre-computed statistics (must agree with transaction history above)
ACCOUNT_STATS: dict[str, dict[str, Any]] = {
    "ACC001": {
        "num_transactions_30d": 5,
        "avg_debit_amount_inr": Decimal("46175.00"),   # mean of 5000+3200+1500+95000 / 4 debits
        "max_debit_30d_inr": Decimal("95000.00"),
        "known_beneficiaries": ["ACC002", "MERCHANT001"],
        "tx_frequency_per_week": 1.25,
        "computation_note": (
            "avg_debit_amount computed from 4 debit transactions in fixture: "
            "(5000+3200+1500+95000)/4 = 26175.00. Rounded to fixture precision."
        ),
    },
    "ACC002": {
        "num_transactions_30d": 2,
        "avg_debit_amount_inr": Decimal("0.00"),       # No debits in fixture
        "max_debit_30d_inr": Decimal("0.00"),
        "known_beneficiaries": [],
        "tx_frequency_per_week": 0.5,
        "computation_note": "ACC002 has only credit transactions in fixture.",
    },
    "ACC003": {
        "num_transactions_30d": 1,
        "avg_debit_amount_inr": Decimal("0.00"),
        "max_debit_30d_inr": Decimal("0.00"),
        "known_beneficiaries": [],
        "tx_frequency_per_week": 0.25,
        "computation_note": "ACC003 account is 2 days old with 1 credit transaction.",
    },
    "ACC004": {
        "num_transactions_30d": 0,
        "avg_debit_amount_inr": Decimal("0.00"),
        "max_debit_30d_inr": Decimal("0.00"),
        "known_beneficiaries": [],
        "tx_frequency_per_week": 0.0,
        "computation_note": "No transactions in the last 30d for ACC004 fixture.",
    },
}

# Fix avg computation: (5000+3200+1500+95000)/4 = 26175.00
ACCOUNT_STATS["ACC001"]["avg_debit_amount_inr"] = Decimal("26175.00")


# ---------------------------------------------------------------------------
# Device registry
# ---------------------------------------------------------------------------

DEVICES: dict[str, dict[str, Any]] = {
    "DEV001": {
        "device_id": "DEV001",
        "device_fingerprint": "synthetic-fp-a1b2c3d4e5f6",
        "device_type": "mobile",
        "device_info": "Synthetic Android 14 — Pixel 7",
        "associated_accounts": ["ACC001"],
        "first_seen": datetime(2022, 7, 1, tzinfo=timezone.utc),
        "registration_status": "REGISTERED",
        "num_associated_accounts": 1,
        "synthetic_notice": SYNTHETIC_DATA_NOTICE,
    },
    "DEV002": {
        "device_id": "DEV002",
        "device_fingerprint": "synthetic-fp-z9y8x7w6v5u4",
        "device_type": "mobile",
        "device_info": "Synthetic iOS 17 — iPhone 15",
        "associated_accounts": [],           # New device; not seen before
        "first_seen": None,
        "registration_status": "NOT_REGISTERED",
        "num_associated_accounts": 0,
        "synthetic_notice": SYNTHETIC_DATA_NOTICE,
    },
    "DEV003": {
        "device_id": "DEV003",
        "device_fingerprint": "synthetic-fp-m1n2o3p4q5r6",
        "device_type": "desktop",
        "device_info": "Synthetic Windows 11 — Chrome 120",
        "associated_accounts": ["ACC001", "ACC003", "ACC004"],  # Shared device
        "first_seen": datetime(2023, 5, 15, tzinfo=timezone.utc),
        "registration_status": "REGISTERED",
        "num_associated_accounts": 3,
        "synthetic_notice": SYNTHETIC_DATA_NOTICE,
    },
}

# Mapping from account → registered device IDs
ACCOUNT_DEVICES: dict[str, list[str]] = {
    "ACC001": ["DEV001", "DEV003"],
    "ACC002": [],
    "ACC003": ["DEV003"],
    "ACC004": ["DEV003"],
}


# ---------------------------------------------------------------------------
# Sanctions / watchlist fixture
# ---------------------------------------------------------------------------

# SANC001: synthetic name that matches the watchlist in the mock
SANCTIONS_SUBJECTS: dict[str, dict[str, Any]] = {
    "SANC001": {
        "subject_name": "Synthetic Fraudster One",
        "subject_id": "SANC001",
        "matched": True,
        "list_name": "SYNTHETIC_WATCHLIST_MOCK",
        "match_detail": "Exact name match on SYNTHETIC mock watchlist entry.",
        "match_confidence": "HIGH",
        "matching_method": "EXACT_NAME",
        "list_date": datetime(2023, 6, 1, tzinfo=timezone.utc),
        "synthetic_notice": (
            "SYNTHETIC — This is a fabricated watchlist match for testing only. "
            "No real sanctions database was consulted."
        ),
    },
    "SANC002": {
        "subject_name": "Clean User (SYNTHETIC)",
        "subject_id": "SANC002",
        "matched": False,
        "list_name": None,
        "match_detail": "No match found in SYNTHETIC mock watchlist.",
        "match_confidence": None,
        "matching_method": "EXACT_NAME",
        "list_date": None,
        "synthetic_notice": (
            "SYNTHETIC — No real sanctions database was consulted."
        ),
    },
}

# Map account IDs to their synthetic sanctions subject key for convenience
ACCOUNT_SANCTIONS_KEY: dict[str, str] = {
    "ACC001": "SANC002",    # Clean
    "ACC002": "SANC002",    # Clean
    "ACC003": "SANC002",    # Clean
    "ACC004": "SANC001",    # Flagged
}


# ---------------------------------------------------------------------------
# Geolocation scenarios
# ---------------------------------------------------------------------------

# Location of the transaction being scored (used in scenario fixtures)
GEOLOCATION_SCENARIOS: dict[str, dict[str, Any]] = {
    "NORMAL_BENGALURU": {
        "scenario_id": "NORMAL_BENGALURU",
        "account_id": "ACC001",
        "transaction_city": "Bengaluru",
        "transaction_state": "Karnataka",
        "transaction_country": "India",
        "transaction_latitude": 12.9716,
        "transaction_longitude": 77.5946,
        "transaction_timestamp": datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        "description": "Transaction origin matches ACC001 registered location.",
    },
    "SUSPICIOUS_DISTANT": {
        "scenario_id": "SUSPICIOUS_DISTANT",
        "account_id": "ACC001",
        "transaction_city": "Moscow",
        "transaction_state": None,
        "transaction_country": "Russia",
        "transaction_latitude": 55.7558,
        "transaction_longitude": 37.6176,
        "transaction_timestamp": datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        "description": (
            "Transaction from Moscow while ACC001 is registered in Bengaluru. "
            "Travel distance ~7,100 km in 0 hours — impossible travel."
        ),
    },
    "MISSING_LOCATION": {
        "scenario_id": "MISSING_LOCATION",
        "account_id": "ACC001",
        "transaction_city": None,
        "transaction_state": None,
        "transaction_country": None,
        "transaction_latitude": None,
        "transaction_longitude": None,
        "transaction_timestamp": datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        "description": "Transaction location data is absent.",
    },
}


# ---------------------------------------------------------------------------
# Synthetic news article fixtures (used by the mock NewsAPI provider)
# ---------------------------------------------------------------------------

NEWS_ARTICLES: dict[str, list[dict[str, Any]]] = {
    "Synthetic Fraudster One": [
        {
            "title": "SYNTHETIC: Authorities Investigate Shell Company Network",
            "source": "Synthetic Financial Times",
            "published_at": "2024-01-10T08:00:00Z",
            "url": "https://synthetic.example.com/article/shell-company-investigation",
            "description": (
                "SYNTHETIC NEWS ARTICLE — This is fabricated test content only. "
                "Authorities are investigating a synthetic shell company network "
                "linked to 'Synthetic Fraudster One'."
            ),
            "synthetic_notice": SYNTHETIC_DATA_NOTICE,
        },
    ],
    "Arjun Sharma (SYNTHETIC)": [],      # No adverse news for normal scenario
    "Priya Menon (SYNTHETIC)": [],
    "Clean User (SYNTHETIC)": [],
    "Risk Subject (SYNTHETIC)": [
        {
            "title": "SYNTHETIC: PEP Disclosure Concerns Raised",
            "source": "Synthetic Regulatory Review",
            "published_at": "2023-12-01T09:30:00Z",
            "url": "https://synthetic.example.com/article/pep-disclosure",
            "description": (
                "SYNTHETIC NEWS ARTICLE — Fabricated test content. "
                "PEP disclosure concerns raised regarding 'Risk Subject (SYNTHETIC)'."
            ),
            "synthetic_notice": SYNTHETIC_DATA_NOTICE,
        },
    ],
}

# Default: no articles returned for any unknown entity
DEFAULT_NO_NEWS: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Helper lookups
# ---------------------------------------------------------------------------

KNOWN_ACCOUNT_IDS = set(ACCOUNTS.keys())
KNOWN_DEVICE_IDS = set(DEVICES.keys())
KNOWN_SANCTIONS_SUBJECTS = set(SANCTIONS_SUBJECTS.keys())


def get_account(account_id: str) -> dict[str, Any] | None:
    """Return the account fixture dict or None for unknown accounts."""
    return ACCOUNTS.get(account_id)


def get_transaction_history(account_id: str) -> list[dict[str, Any]]:
    """Return the transaction history list for an account (empty if unknown)."""
    return TRANSACTION_HISTORY.get(account_id, [])


def get_account_stats(account_id: str) -> dict[str, Any] | None:
    """Return pre-computed statistics for an account or None if unknown."""
    return ACCOUNT_STATS.get(account_id)


def get_device(device_id: str) -> dict[str, Any] | None:
    """Return device fixture or None if unknown."""
    return DEVICES.get(device_id)


def get_account_devices(account_id: str) -> list[str]:
    """Return list of registered device IDs for an account."""
    return ACCOUNT_DEVICES.get(account_id, [])


def is_device_registered_to_account(account_id: str, device_id: str) -> bool:
    """Return True if device_id is in the registered devices for account_id."""
    return device_id in get_account_devices(account_id)


def get_sanctions_result(subject_key: str) -> dict[str, Any] | None:
    """Return sanctions fixture by subject key (SANC001, SANC002...) or None."""
    return SANCTIONS_SUBJECTS.get(subject_key)


def get_account_sanctions_result(account_id: str) -> dict[str, Any] | None:
    """Return the sanctions fixture for an account (via ACCOUNT_SANCTIONS_KEY)."""
    key = ACCOUNT_SANCTIONS_KEY.get(account_id)
    if key is None:
        return None
    return SANCTIONS_SUBJECTS.get(key)


def get_news_articles(entity_name: str) -> list[dict[str, Any]]:
    """Return synthetic news articles for an entity name (empty list if unknown)."""
    return NEWS_ARTICLES.get(entity_name, DEFAULT_NO_NEWS)
