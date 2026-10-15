# FILE: docs/04_MACHINE_LEARNING/ISOLATION_FOREST_PIPELINE.md

# Isolation Forest Anomaly Detection Pipeline

## Status

**IMPLEMENTED AND VERIFIED** — Phase 2 secondary unsupervised model.

## Purpose

Isolation Forest provides an unsupervised cross-check on the XGBoost fraud
signal. It detects statistically unusual transactions without using fraud labels
during training.

Used by Agent 1 (Anomaly Detector) alongside the XGBoost primary model.

## Critical distinction

Isolation Forest is unsupervised. It detects anomalies, not fraud.
**Anomaly ≠ Fraud.**

The IF score and the XGBoost `fraud_probability` have different meanings and
scales. They must not be combined into a single score unless a tested fusion
strategy exists.

## Source Modules

| Module | Path | Responsibility |
|---|---|---|
| IF Trainer | `src/ml/if_trainer.py` | Unsupervised training, artifact persistence |
| IF Predictor | `src/ml/if_predictor.py` | Inference from saved artifacts |
| IF Evaluator | `src/ml/if_evaluator.py` | Evaluation metrics against fraud labels |

Shared with XGBoost:

| Module | Path | Shared responsibility |
|---|---|---|
| Loader | `src/ml/ieee_cis_loader.py` | IEEE-CIS data loading and merging |
| Preprocessor | `src/ml/preprocessor.py` | Feature engineering pipeline |

## Training Script

```
python scripts/train_isolation_forest.py
```

Environment variable overrides:

| Variable | Default | Description |
|---|---|---|
| `SENTINEL_DATA_DIR` | `dataset/raw/ieee_cis` | IEEE-CIS data directory |
| `SENTINEL_IF_MODEL_DIR` | `models/isolation_forest` | IF artifact directory |
| `SENTINEL_XGB_PREP_PATH` | (not set) | Path to existing XGBoost `preprocessor.joblib` to reuse |
| `SENTINEL_SAMPLE_FRAC` | (full) | Float in (0,1] to subsample for speed |

## Preprocessing

The IF pipeline reuses the same `build_preprocessing_pipeline` / `get_feature_names`
functions from `src/ml/preprocessor.py` used by XGBoost.

Two modes:

1. **Standalone** (default): A fresh preprocessor is fitted on the IF training
   split and saved as `preprocessor.joblib` in the IF artifact directory.

2. **Shared** (`SENTINEL_XGB_PREP_PATH` set): The existing XGBoost preprocessor
   is loaded. This is only safe when both models are trained on the same feature
   distribution. The preprocessor is not duplicated in the IF artifact directory.

No second competing preprocessing pipeline exists.

## Unsupervised Training

`IsolationForest.fit()` receives **only the feature matrix (X_train)**.
Fraud labels (y) are never passed to the model.
Labels are kept separately and used only for evaluation.

## Score Convention

```
anomaly_score = -IsolationForest.score_samples(X)
```

Higher `anomaly_score` = more anomalous.

This negation makes the score direction consistent with XGBoost's
`fraud_probability` (higher = greater concern), while keeping the two
signals clearly separate and differently named.

The score is **not** a probability. It is a relative unusualness measure.

## Contamination Parameter

Default: `'auto'` (sklearn's internal decision boundary, not tied to
the observed fraud rate).

The contamination parameter is deliberately NOT set to the fraud base rate.
The model does not know what fraction of transactions are fraudulent;
setting contamination to the fraud rate would leak class information.

## Decision Thresholds

- **Trivial Baseline Threshold**: `0.0` (model's natural decision boundary where `score_samples == 0`). Flags all transactions (FPR=1.000, FNR=0.000, F1=0.0687).
- **Calibrated Threshold**: `0.4679` (selected via F1-maximization on held-out validation/calibration split). FPR drops to `0.0346` (3.5% false alarms), F1=`0.2933`, Precision=`0.2618`, Recall=`0.3333`, Accuracy=`0.9315`.
- Calibration script: `scripts/run_threshold_calibration.py`.
- Full details: `THRESHOLD_CALIBRATION.md`.

## Artifacts

Saved to `models/isolation_forest/v1/` (gitignored):

| File | Contents |
|---|---|
| `if_model.joblib` | Fitted IsolationForest |
| `feature_names.joblib` | Ordered feature name list |
| `preprocessor.joblib` | Standalone preprocessor (standalone mode only) |
| `metadata.json` | Version, timestamp, params, score convention, caveats |
| `evaluation_test.json` | Held-out test metrics at baseline threshold=0.0 |
| `evaluation_test_calibrated.json` | Held-out test metrics at calibrated threshold=0.468 |
| `threshold_calibration.json` | Selected threshold metadata and optimization objective |

## Inference & Feature Mapping Interface

```python
from src.ml.if_predictor import AnomalyPredictor
from src.ml.feature_mapper import canonical_to_if_features

predictor = AnomalyPredictor()  # loads once, never retrains
scores = predictor.score(X_df)  # np.ndarray, higher = more anomalous

# Single-transaction inference from raw feature dict
result = predictor.score_transaction({"TransactionAmt": 250.0, ...})
# result["anomaly_score"]  — float, NOT a probability
# result["is_anomaly"]     — bool
# result["score_note"]     — explicit disclaimer

# Single-transaction inference from CanonicalTransaction
features = canonical_to_if_features(canonical_tx)
result = predictor.score_transaction(features)
```

## Integration with Sentinel AI

The `score_transaction()` output is consumed by `Agent1Scorer` (`src/ml/agent1_scorer.py`).

The IF `anomaly_score` and the XGBoost `fraud_probability` are kept in
separate dicts with different key names. They are reported separately.
No combined score is produced without a tested fusion strategy.

## Separation from XGBoost

| Dimension | XGBoost | Isolation Forest |
|---|---|---|
| Training | Supervised (uses labels) | Unsupervised (no labels) |
| Output key | `fraud_probability` | `anomaly_score` |
| Output range | [0, 1] probability | ℝ, not a probability |
| Higher means | More likely fraud | More anomalous |
| Evaluation | Against IEEE-CIS labels | Against IEEE-CIS labels (correlation only) |
| Artifact dir | `models/xgboost/v1/` | `models/isolation_forest/v1/` |

## Testing & Verification

Automated tests covering Isolation Forest training, prediction, scoring, and evaluation:

```bash
.venv/bin/python -m pytest tests/test_if_trainer.py tests/test_if_predictor.py tests/test_if_evaluator.py -v
```

Total project test suite: **265 tests passing** (`.venv/bin/python -m pytest tests/`).
