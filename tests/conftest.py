"""
Shared pytest fixtures for Sentinel AI ML pipeline tests.

All fixtures use small synthetic DataFrames that mimic the IEEE-CIS schema
without containing real data.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Live-service configuration
# ---------------------------------------------------------------------------
# Live Neo4j integration tests skip unless NEO4J_* variables are present.
# Load ONLY the NEO4J_* keys from the project .env (never API keys, so the
# offline unit tests keep using mock providers). Variables already exported
# in the shell take precedence.
def _load_neo4j_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import dotenv_values
    except ImportError:
        return
    for key, value in dotenv_values(env_path).items():
        if key.startswith("NEO4J_") and value and key not in os.environ:
            os.environ[key] = value


_load_neo4j_env()

# Agent 5 must never call a real LLM from the offline suite, even when the
# shell exports GROQ_API_KEY. Live LLM tests opt in explicitly
# (SENTINEL_LIVE_LLM_TESTS=1) and build their own client.
os.environ["SENTINEL_REPORT_GENERATOR"] = "template"


# ---------------------------------------------------------------------------
# Dataset fixture helpers
# ---------------------------------------------------------------------------

def _make_ieee_cis_fixture(n: int = 400, fraud_frac: float = 0.10, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    """Return (X, y) with a tiny synthetic IEEE-CIS-like DataFrame.

    Includes:
    - A subset of numeric columns (TransactionAmt, card1, D1, V1..V10, C1..C5)
    - A few categorical columns (ProductCD, card4, card6, M1, DeviceType)
    - Missing values in some numeric columns (realistic)
    - No TransactionID or isFraud in X
    """
    rng = np.random.RandomState(seed)
    n_fraud = max(2, int(n * fraud_frac))
    n_legit = n - n_fraud

    def rand_col(size, nan_frac=0.0):
        arr = rng.uniform(0, 1000, size).astype(float)
        if nan_frac > 0:
            mask = rng.random(size) < nan_frac
            arr[mask] = np.nan
        return arr

    X = pd.DataFrame({
        "TransactionDT": rng.randint(86400, 15811131, n),
        "TransactionAmt": rng.exponential(100, n),
        "ProductCD": rng.choice(["W", "H", "C", "S", "R"], n),
        "card1": rng.randint(1000, 9999, n).astype(float),
        "card2": rand_col(n, nan_frac=0.1),
        "card3": rand_col(n, nan_frac=0.05),
        "card4": rng.choice(["visa", "mastercard", "american express", None], n),
        "card5": rand_col(n, nan_frac=0.05),
        "card6": rng.choice(["debit", "credit", None], n),
        "addr1": rand_col(n, nan_frac=0.15),
        "addr2": rand_col(n, nan_frac=0.15),
        "dist1": rand_col(n, nan_frac=0.5),
        "dist2": rand_col(n, nan_frac=0.7),
        "P_emaildomain": rng.choice(["gmail.com", "yahoo.com", "hotmail.com", None], n),
        "R_emaildomain": rng.choice(["gmail.com", "yahoo.com", None, "anonymous.com"], n),
        "C1": rand_col(n),
        "C2": rand_col(n),
        "C3": rand_col(n, nan_frac=0.2),
        "C4": rand_col(n, nan_frac=0.3),
        "C5": rand_col(n),
        "D1": rand_col(n, nan_frac=0.3),
        "D2": rand_col(n, nan_frac=0.5),
        "D3": rand_col(n, nan_frac=0.5),
        "M1": rng.choice(["T", "F", None], n),
        "M2": rng.choice(["T", "F", None], n),
        "M3": rng.choice(["T", "F", None], n),
        "V1": rand_col(n, nan_frac=0.3),
        "V2": rand_col(n, nan_frac=0.3),
        "V3": rand_col(n, nan_frac=0.3),
        "DeviceType": rng.choice(["desktop", "mobile", None], n),
        "DeviceInfo": rng.choice(["Windows", "iOS Device", "MacOS", None], n),
        "id_01": rand_col(n, nan_frac=0.4),
        "id_02": rand_col(n, nan_frac=0.4),
    })

    # Build target: frauds have higher transaction amounts on average
    labels = np.zeros(n, dtype=int)
    fraud_idx = rng.choice(n, n_fraud, replace=False)
    labels[fraud_idx] = 1
    y = pd.Series(labels, name="isFraud")

    return X, y


@pytest.fixture
def small_ieee_cis_fixture() -> tuple[pd.DataFrame, pd.Series]:
    """Small (400-row) synthetic IEEE-CIS-like dataset fixture."""
    return _make_ieee_cis_fixture(n=400, fraud_frac=0.10)


@pytest.fixture
def tiny_ieee_cis_fixture() -> tuple[pd.DataFrame, pd.Series]:
    """Tiny (100-row) fixture for fast unit tests."""
    return _make_ieee_cis_fixture(n=100, fraud_frac=0.15)
