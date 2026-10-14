"""
Sentinel AI — SHAP-based explainability.

Purpose
-------
Provide global feature importance and per-prediction explanation for the
XGBoost model.

Distinction
-----------
SHAP values show which features contributed most to a particular prediction.
They describe the model's reasoning, NOT proof that the transaction is
fraudulent.  This distinction must be preserved in any downstream report.

Usage
-----
Global importance:
    summary = global_importance(model, X_transformed, feature_names)

Single-prediction explanation:
    explanation = explain_prediction(model, x_row, feature_names)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import shap

logger = logging.getLogger(__name__)

# Reuse a single TreeExplainer per model instance to avoid rebuilding the
# background distribution on every call.
_explainer_cache: dict[int, shap.TreeExplainer] = {}


def _get_explainer(model: Any) -> shap.TreeExplainer:
    """Return a cached or newly created TreeExplainer for *model*."""
    model_id = id(model)
    if model_id not in _explainer_cache:
        logger.info("Creating SHAP TreeExplainer (model id=%d) …", model_id)
        _explainer_cache[model_id] = shap.TreeExplainer(model)
    return _explainer_cache[model_id]


def global_importance(
    model: Any,
    X_transformed: np.ndarray,
    feature_names: list[str],
    *,
    max_display: int = 20,
    background_sample: int = 500,
    random_state: int = 42,
) -> pd.DataFrame:
    """Compute mean |SHAP| importance across a sample of rows.

    Parameters
    ----------
    model          : fitted XGBClassifier
    X_transformed  : preprocessed numpy array (output of pipeline.transform)
    feature_names  : ordered list of feature names
    max_display    : number of top features to return
    background_sample : number of rows to sample for speed
    random_state   : seed for reproducible sampling

    Returns
    -------
    pd.DataFrame with columns [feature, mean_abs_shap]
    sorted descending by importance.
    """
    rng = np.random.RandomState(random_state)
    n = min(background_sample, len(X_transformed))
    idx = rng.choice(len(X_transformed), size=n, replace=False)
    sample = X_transformed[idx]

    explainer = _get_explainer(model)
    shap_values = explainer.shap_values(sample)

    mean_abs = np.abs(shap_values).mean(axis=0)
    importance_df = (
        pd.DataFrame({"feature": feature_names, "mean_abs_shap": mean_abs})
        .sort_values("mean_abs_shap", ascending=False)
        .head(max_display)
        .reset_index(drop=True)
    )
    logger.info("Global SHAP importance computed (top %d features).", max_display)
    return importance_df


def explain_prediction(
    model: Any,
    x_row: np.ndarray,
    feature_names: list[str],
    *,
    top_n: int = 10,
) -> dict[str, Any]:
    """Explain a single prediction with SHAP values.

    Parameters
    ----------
    model        : fitted XGBClassifier
    x_row        : 1-D numpy array (single preprocessed transaction row)
    feature_names: ordered feature name list
    top_n        : number of top contributors to return

    Returns
    -------
    dict with:
        base_value          : SHAP expected value (log-odds of base rate)
        shap_sum            : sum of SHAP values (= prediction log-odds shift)
        top_contributors    : list of {feature, shap_value, direction}
        explanation_note    : disclaimer string
    """
    x_2d = x_row.reshape(1, -1)
    explainer = _get_explainer(model)
    shap_values = explainer.shap_values(x_2d)[0]
    base_value = float(explainer.expected_value)

    contributors = sorted(
        zip(feature_names, shap_values.tolist()),
        key=lambda t: abs(t[1]),
        reverse=True,
    )[:top_n]

    return {
        "base_value": round(base_value, 6),
        "shap_sum": round(float(shap_values.sum()), 6),
        "top_contributors": [
            {
                "feature": name,
                "shap_value": round(val, 6),
                "direction": "increases_fraud_score" if val > 0 else "decreases_fraud_score",
            }
            for name, val in contributors
        ],
        "explanation_note": (
            "SHAP values indicate this model's feature attribution for this prediction. "
            "They describe model behaviour, not proof of fraudulent intent."
        ),
    }
