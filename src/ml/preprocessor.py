"""
Sentinel AI — Feature engineering and sklearn preprocessing pipeline.

Design principles
-----------------
* Fitted *only* on training data; transforms applied identically at inference.
* Reusable by the future Isolation Forest implementation.
* Reusable by Sentinel AI inference via :func:`build_inference_pipeline`.
* Produces a serialisable ``sklearn.pipeline.Pipeline`` artifact.

IEEE-CIS column taxonomy
------------------------
The dataset contains six groups of anonymised columns:

* TransactionAmt, ProductCD    — transaction-level descriptors
* card1–card6                  — card attributes (mix of numeric / categorical)
* addr1, addr2                 — billing / shipping address codes
* dist1, dist2                 — distance features
* P_emaildomain, R_emaildomain — email domain (categorical)
* C1–C14                       — counting features
* D1–D15                       — timedelta features
* M1–M9                        — boolean match flags (T/F/NaN → categorical)
* V1–V339                      — Vesta-engineered features (numeric)
* id_01–id_38, DeviceType,     — identity columns (mix of numeric / categorical)
  DeviceInfo

Leakage notes
-------------
* TransactionID removed in the loader (identifier).
* isFraud removed in the loader (label).
* TransactionDT is a relative timedelta; it does NOT encode wall-clock time, so
  it does not introduce temporal leakage in the cross-sectional split used here.
  It is kept as a numeric feature.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# Columns that are purely categorical (non-ordinal; encoded with OrdinalEncoder
# because XGBoost handles integer codes efficiently and avoids dimensionality
# explosion from one-hot encoding on high-cardinality columns).
_CATEGORICAL_COLS: List[str] = [
    "ProductCD",
    "card4",
    "card6",
    "P_emaildomain",
    "R_emaildomain",
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6",
    "M7",
    "M8",
    "M9",
    "id_12",
    "id_15",
    "id_16",
    "id_23",
    "id_27",
    "id_28",
    "id_29",
    "id_30",
    "id_31",
    "id_33",
    "id_34",
    "id_35",
    "id_36",
    "id_37",
    "id_38",
    "DeviceType",
    "DeviceInfo",
]

# Numeric columns that may have missings — imputed with median then kept.
# All remaining float/int columns not in the categorical list fall here.
# (Determined dynamically in build_pipeline to avoid hard-coding V1..V339.)


def _get_numeric_cols(X: pd.DataFrame) -> List[str]:
    """Return numeric column names excluding categoricals."""
    cat_set = set(_CATEGORICAL_COLS)
    return [
        c
        for c in X.columns
        if c not in cat_set and X[c].dtype in (np.float64, np.float32, np.int64, np.int32, int, float)
    ]


def _get_categorical_present(X: pd.DataFrame) -> List[str]:
    """Return categorical columns that actually exist in X."""
    return [c for c in _CATEGORICAL_COLS if c in X.columns]


# ---------------------------------------------------------------------------
# Pipeline builder
# ---------------------------------------------------------------------------


def build_preprocessing_pipeline(X_train: pd.DataFrame) -> Pipeline:
    """Build and fit a preprocessing pipeline on *X_train*.

    Steps:
    1. Numeric imputation (median strategy — robust to outliers).
    2. Categorical imputation (constant 'MISSING') + OrdinalEncoder
       (unknown categories at inference become -1, not an error).

    Parameters
    ----------
    X_train:
        Training feature matrix (leakage columns already removed).

    Returns
    -------
    fitted_pipeline : sklearn.pipeline.Pipeline
        A fitted ``ColumnTransformer``-based pipeline ready to transform
        both training and inference data.
    """
    num_cols = _get_numeric_cols(X_train)
    cat_cols = _get_categorical_present(X_train)

    logger.info(
        "Building preprocessing pipeline: %d numeric, %d categorical features.",
        len(num_cols),
        len(cat_cols),
    )

    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )

    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="MISSING")),
            (
                "encoder",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                    dtype=np.float64,
                ),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, num_cols),
            ("cat", categorical_transformer, cat_cols),
        ],
        remainder="drop",  # explicitly drop any leftover columns
        verbose_feature_names_out=False,
    )

    pipeline = Pipeline(steps=[("preprocessor", preprocessor)])
    pipeline.fit(X_train)

    logger.info("Preprocessing pipeline fitted successfully.")
    return pipeline


def get_feature_names(pipeline: Pipeline, X_train: pd.DataFrame) -> List[str]:
    """Return ordered feature names produced by the fitted pipeline.

    Parameters
    ----------
    pipeline : fitted Pipeline from build_preprocessing_pipeline
    X_train  : the DataFrame used to fit the pipeline

    Returns
    -------
    List of feature name strings in the same column order as the
    transformed array.
    """
    num_cols = _get_numeric_cols(X_train)
    cat_cols = _get_categorical_present(X_train)
    return num_cols + cat_cols
