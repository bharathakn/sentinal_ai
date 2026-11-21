"""
Sentinel AI — India-native behavioural model for Agent 1 (Phase 9.5).

Why
---
The IEEE-CIS models score India transactions with ~430 of ~434 features
imputed, so their output is near-constant for India cases. This module trains
XGBoost + Isolation Forest directly on behavioural features of the Custom
Synthetic India Dataset.

Train / serve parity
--------------------
Features are extracted from a `CanonicalTransaction` by `extract_features()`
in BOTH training (rows → IndiaSyntheticAdapter → CanonicalTransaction) and
scoring. There is no separate training-only feature path.

Feature policy
--------------
Behavioural deviation features only. Signals that Agent 4 already scores
independently are EXCLUDED to avoid double counting in the risk score:
is_new_device, is_new_beneficiary, distance_from_home_km and
time_since_beneficiary_added_min.

Label firewall
--------------
Labels (is_fraud) are read from transactions_targets.csv by the trainer only,
joined by transaction_id. `extract_features()` never reads label fields.

Caveat
------
Labels are SYNTHETIC and were produced by a rule-based generator. Metrics on
this data are optimistic relative to real-world fraud detection and must be
reported as synthetic-data metrics.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..schemas.canonical_transaction import CanonicalTransaction

logger = logging.getLogger(__name__)

MODEL_VERSION = "india_behaviour_v1"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "india_behaviour" / "v1"

FEATURES: list[str] = [
    "log_amount",
    "amount_ratio_vs_30d_avg",
    "log_amount_ratio",
    "tx_frequency_24h",
    "log_time_since_last_tx",
    "balance_drain_ratio",
    "hour_of_day",
    "is_night",
    "day_of_week",
    "channel_upi",
    "channel_neft",
    "channel_rtgs",
]

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "log_amount": "log(1 + transaction amount)",
    "amount_ratio_vs_30d_avg": "amount relative to the sender's 30-day average",
    "log_amount_ratio": "log of the amount ratio",
    "tx_frequency_24h": "sender transactions in the last 24 hours",
    "log_time_since_last_tx": "log(1 + seconds since the sender's previous transaction)",
    "balance_drain_ratio": "amount as a fraction of the balance before the transaction",
    "hour_of_day": "local hour of the transaction",
    "is_night": "local time between 23:00 and 05:59",
    "day_of_week": "day of week (0 = Monday)",
    "channel_upi": "UPI channel",
    "channel_neft": "NEFT channel",
    "channel_rtgs": "RTGS channel",
}


def _f(v: Any) -> float:
    if v is None:
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def extract_features(tx: CanonicalTransaction) -> dict[str, float]:
    """Behavioural features from a CanonicalTransaction (NaN when unavailable)."""
    md = tx.metadata
    amount = _f(tx.amount)
    ratio = _f(md.amount_ratio_vs_30d_avg) if md else float("nan")
    since = _f(md.time_since_last_tx_sec) if md else float("nan")
    bal = _f(tx.sender.balance_before) if tx.sender else float("nan")
    hour = float(tx.timestamp.hour) if tx.timestamp else float("nan")
    channel = str(getattr(tx.channel, "value", tx.channel)).upper()
    return {
        "log_amount": math.log1p(amount) if amount == amount and amount >= 0 else float("nan"),
        "amount_ratio_vs_30d_avg": ratio,
        "log_amount_ratio": math.log(ratio) if ratio == ratio and ratio > 0 else float("nan"),
        "tx_frequency_24h": _f(md.tx_frequency_24h) if md else float("nan"),
        "log_time_since_last_tx": math.log1p(since) if since == since and since >= 0 else float("nan"),
        "balance_drain_ratio": (amount / bal) if bal == bal and bal > 0 else float("nan"),
        "hour_of_day": hour,
        "is_night": float(hour >= 23 or hour < 6) if hour == hour else float("nan"),
        "day_of_week": float(tx.timestamp.weekday()) if tx.timestamp else float("nan"),
        "channel_upi": float(channel == "UPI"),
        "channel_neft": float(channel == "NEFT"),
        "channel_rtgs": float(channel == "RTGS"),
    }


def feature_coverage(feats: dict[str, float]) -> int:
    return sum(1 for v in feats.values() if v == v)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def _best_f1_threshold(y: np.ndarray, scores: np.ndarray) -> float:
    from sklearn.metrics import precision_recall_curve

    p, r, t = precision_recall_curve(y, scores)
    f1 = 2 * p * r / np.clip(p + r, 1e-12, None)
    i = int(np.nanargmax(f1[:-1])) if len(t) else 0
    return float(t[i]) if len(t) else 0.5


def _metrics(y: np.ndarray, scores: np.ndarray, thr: float) -> dict[str, float]:
    from sklearn.metrics import (average_precision_score, f1_score, precision_score,
                                 recall_score, roc_auc_score)

    pred = (scores >= thr).astype(int)
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    return {
        "threshold": round(float(thr), 6),
        "roc_auc": round(float(roc_auc_score(y, scores)), 4),
        "pr_auc": round(float(average_precision_score(y, scores)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "fpr": round(fp / max(fp + tn, 1), 4),
        "positives": int(y.sum()),
        "n": int(len(y)),
    }


def train(data_dir: Path, out_dir: Path = DEFAULT_MODEL_DIR, seed: int = 42) -> dict[str, Any]:
    """Train and save the India behavioural XGBoost + Isolation Forest models.

    Split: stratified 70/15/15 train/validation/test. Thresholds are chosen on
    validation (F1-max); the test split is evaluated exactly once.
    """
    import joblib
    import pandas as pd
    from sklearn.ensemble import IsolationForest
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    from ..schemas.adapters.india_adapter import IndiaSyntheticAdapter

    data_dir = Path(data_dir)
    feats_df = pd.read_csv(data_dir / "transactions_features.csv")
    labels = pd.read_csv(data_dir / "transactions_targets.csv")[["transaction_id", "is_fraud"]]
    X = pd.DataFrame(
        [extract_features(IndiaSyntheticAdapter.from_row(r)) for r in feats_df.to_dict("records")],
        columns=FEATURES,
    )
    y = feats_df[["transaction_id"]].merge(labels, on="transaction_id", how="left")["is_fraud"].astype(int).to_numpy()

    idx = np.arange(len(X))
    tr, rest = train_test_split(idx, test_size=0.30, stratify=y, random_state=seed)
    va, te = train_test_split(rest, test_size=0.50, stratify=y[rest], random_state=seed)

    pos = max(int(y[tr].sum()), 1)
    xgb = XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9,
        scale_pos_weight=(len(tr) - pos) / pos, eval_metric="aucpr", random_state=seed, n_jobs=2,
    )
    xgb.fit(X.iloc[tr], y[tr])
    iso = IsolationForest(n_estimators=200, contamination="auto", random_state=seed)
    iso.fit(X.iloc[tr].fillna(X.iloc[tr].median()))
    medians = X.iloc[tr].median().to_dict()

    def xgb_scores(rows):
        return xgb.predict_proba(X.iloc[rows])[:, 1]

    def if_scores(rows):
        return -iso.score_samples(X.iloc[rows].fillna(medians))

    xgb_thr = _best_f1_threshold(y[va], xgb_scores(va))
    if_thr = _best_f1_threshold(y[va], if_scores(va))
    metrics = {
        "xgboost": {"validation": _metrics(y[va], xgb_scores(va), xgb_thr),
                    "test": _metrics(y[te], xgb_scores(te), xgb_thr)},
        "isolation_forest": {"validation": _metrics(y[va], if_scores(va), if_thr),
                             "test": _metrics(y[te], if_scores(te), if_thr)},
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(xgb, out_dir / "xgb_model.joblib")
    joblib.dump(iso, out_dir / "if_model.joblib")
    metadata = {
        "model_version": MODEL_VERSION,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "Custom Synthetic India Dataset",
        "dataset_dir": str(data_dir),
        "seed": seed,
        "features": FEATURES,
        "if_fill_medians": {k: (None if v != v else float(v)) for k, v in medians.items()},
        "xgb_threshold": xgb_thr,
        "if_threshold": if_thr,
        "split": {"train": len(tr), "validation": len(va), "test": len(te)},
        "label": "is_fraud (BORDERLINE counted as 0)",
        "metrics": metrics,
        "caveat": (
            "SYNTHETIC labels from a rule-based generator; metrics are optimistic and "
            "are not comparable with real-world fraud detection performance."
        ),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    return metadata


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class IndiaBehaviourScorer:
    """Loads the India behavioural artifacts and scores CanonicalTransactions."""

    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR) -> None:
        import joblib

        model_dir = Path(model_dir)
        meta_path = model_dir / "metadata.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"India behaviour model not found at {model_dir}")
        self.metadata = json.loads(meta_path.read_text())
        if self.metadata.get("features") != FEATURES:
            raise ValueError("India model feature list does not match this code version; retrain.")
        self._xgb = joblib.load(model_dir / "xgb_model.joblib")
        self._iso = joblib.load(model_dir / "if_model.joblib")
        self._medians = {k: (np.nan if v is None else v) for k, v in self.metadata["if_fill_medians"].items()}
        self.xgb_threshold = float(self.metadata["xgb_threshold"])
        self.if_threshold = float(self.metadata["if_threshold"])
        self.model_version = self.metadata["model_version"]

    def score(self, tx: CanonicalTransaction, top_n: int = 8) -> dict[str, Any]:
        import pandas as pd

        from .explainer import explain_prediction

        feats = extract_features(tx)
        X = pd.DataFrame([feats], columns=FEATURES)
        prob = float(self._xgb.predict_proba(X)[0, 1])
        if_score = float(-self._iso.score_samples(X.fillna(self._medians))[0])
        shap = None
        try:
            shap = explain_prediction(self._xgb, X.to_numpy(dtype=float)[0], FEATURES, top_n=top_n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("India SHAP failed: %s", exc)
        return {
            "features": feats,
            "fraud_probability": prob,
            "xgb_threshold": self.xgb_threshold,
            "if_anomaly_score": if_score,
            "if_threshold": self.if_threshold,
            "shap": shap,
            "model_version": self.model_version,
        }
