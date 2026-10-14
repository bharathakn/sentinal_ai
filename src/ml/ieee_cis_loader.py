"""
Sentinel AI — IEEE-CIS dataset loader.

Loads and merges train_transaction.csv and train_identity.csv on the shared
TransactionID key, exactly as required by the competition data card.

Rules
-----
* Only the labeled training split (train_*.csv) is used for supervised evaluation.
* The competition test split (test_*.csv) has no isFraud labels and must NOT be
  used for performance reporting.
* TransactionID is excluded from model features (identifier leakage risk).
* isFraud is the ground-truth target column.
* This module reads the raw files without modification; feature engineering lives
  in preprocessor.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Default paths relative to the repository root.
_DEFAULT_IEEE_CIS_DIR = Path("dataset/raw/ieee_cis")

TRANSACTION_JOIN_KEY = "TransactionID"
TARGET_COLUMN = "isFraud"

# Columns that must not appear in the feature matrix.
# TransactionID is a row identifier; isFraud is the label.
LEAKAGE_COLUMNS = {TRANSACTION_JOIN_KEY, TARGET_COLUMN}


def load_ieee_cis(
    data_dir: str | Path | None = None,
    *,
    sample_frac: float | None = None,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load, merge, and return (X, y) for the IEEE-CIS labeled training data.

    Parameters
    ----------
    data_dir:
        Directory containing train_transaction.csv and train_identity.csv.
        Defaults to ``dataset/raw/ieee_cis`` relative to the current working
        directory (i.e. the repository root).
    sample_frac:
        If given, sample this fraction of rows for fast experimentation.
        Must be in (0, 1].  ``None`` loads the full dataset.
    random_state:
        Seed for reproducible sampling.

    Returns
    -------
    X : pd.DataFrame
        Feature matrix with TransactionID and isFraud removed.
    y : pd.Series
        Binary target (0 = legitimate, 1 = fraud).

    Raises
    ------
    FileNotFoundError
        If the expected CSV files are not found in *data_dir*.
    ValueError
        If *sample_frac* is out of range.
    """
    if data_dir is None:
        data_dir = _DEFAULT_IEEE_CIS_DIR
    data_dir = Path(data_dir)

    tx_path = data_dir / "train_transaction.csv"
    id_path = data_dir / "train_identity.csv"

    for p in (tx_path, id_path):
        if not p.exists():
            raise FileNotFoundError(
                f"Expected IEEE-CIS file not found: {p}\n"
                "Place the Kaggle competition files in dataset/raw/ieee_cis/."
            )

    if sample_frac is not None and not (0 < sample_frac <= 1):
        raise ValueError(f"sample_frac must be in (0, 1], got {sample_frac}")

    logger.info("Loading IEEE-CIS train_transaction.csv …")
    tx_df = pd.read_csv(tx_path)
    logger.info("  Loaded %d transaction rows, %d cols.", len(tx_df), tx_df.shape[1])

    logger.info("Loading IEEE-CIS train_identity.csv …")
    id_df = pd.read_csv(id_path)
    logger.info("  Loaded %d identity rows, %d cols.", len(id_df), id_df.shape[1])

    # Left-join: keep all transactions; identity data is optional.
    logger.info("Merging on %s (left join) …", TRANSACTION_JOIN_KEY)
    merged = tx_df.merge(id_df, on=TRANSACTION_JOIN_KEY, how="left")
    logger.info(
        "  Merged shape: %d rows, %d cols.",
        merged.shape[0],
        merged.shape[1],
    )

    if sample_frac is not None:
        merged = merged.sample(frac=sample_frac, random_state=random_state)
        logger.info("  Sampled %.1f%% → %d rows.", sample_frac * 100, len(merged))

    y = merged[TARGET_COLUMN].astype(int)
    X = merged.drop(columns=list(LEAKAGE_COLUMNS))

    fraud_rate = y.mean() * 100
    logger.info(
        "  Fraud rate: %.3f%% (%d positive / %d total)",
        fraud_rate,
        y.sum(),
        len(y),
    )

    return X, y
