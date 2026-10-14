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

## Default Decision Threshold

Default: `0.0` (the model's natural decision boundary where
`score_samples == 0`).

Adjust on held-out data for operational sensitivity requirements.

## Artifacts

Saved to `models/isolation_forest/v1/` (gitignored):

| File | Contents |
|---|---|
| `if_model.joblib` | Fitted IsolationForest |
| `feature_names.joblib` | Ordered feature name list |
| `preprocessor.joblib` | Standalone preprocessor (standalone mode only) |
| `metadata.json` | Version, timestamp, params, score convention, caveats |
| `evaluation_test.json` | Held-out test metrics |

## Inference Interface

```python
from src.ml.if_predictor import AnomalyPredictor

predictor = AnomalyPredictor()  # loads once, never retrains
scores = predictor.score(X_df)  # np.ndarray, higher = more anomalous

# Single-transaction (Agent 1 integration point)
result = predictor.score_transaction({"TransactionAmt": 250.0, ...})
# result["anomaly_score"]  — float, NOT a probability
# result["is_anomaly"]     — bool
# result["score_note"]     — explicit disclaimer
```

## Integration with Sentinel AI

The `score_transaction()` output is the Agent 1 entry point.

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

## Testing

109 total tests (61 XGBoost + 48 IF). Run with:

```
.venv/bin/python -m pytest tests/ -v
```

IF-specific test files:
- `tests/test_if_trainer.py`
- `tests/test_if_predictor.py`
- `tests/test_if_evaluator.py`
