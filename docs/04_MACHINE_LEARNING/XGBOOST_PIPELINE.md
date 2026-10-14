# FILE: docs/04_MACHINE_LEARNING/XGBOOST_PIPELINE.md

# XGBoost Fraud Detection Pipeline

## Status

**IMPLEMENTED AND VERIFIED** — Phase 2 primary supervised model.

## Overview

XGBoost binary classifier trained on the IEEE-CIS Fraud Detection dataset.
Used as the primary model for Agent 1 (Anomaly Detector).

## Dataset

IEEE-CIS Fraud Detection Dataset.

- Training transactions: 590,540 rows, 394 columns.
- Identity rows: 144,233 rows, 41 columns.
- Merge key: `TransactionID` (left join — all transactions retained).
- Target column: `isFraud` (binary, 0 = legitimate, 1 = fraud).
- Fraud base rate: ~3.5% (severe class imbalance).
- Unlabeled competition test split excluded from all performance reporting.

## Source Modules

| Module | Path | Responsibility |
|---|---|---|
| Loader | `src/ml/ieee_cis_loader.py` | Load and merge IEEE-CIS CSVs |
| Preprocessor | `src/ml/preprocessor.py` | Feature engineering + sklearn pipeline |
| Trainer | `src/ml/trainer.py` | Train, split, save artifacts |
| Predictor | `src/ml/predictor.py` | Inference from saved artifacts |
| Evaluator | `src/ml/evaluator.py` | Metrics calculation and reporting |
| Explainer | `src/ml/explainer.py` | SHAP global and per-prediction attribution |

## Training Script

```
python scripts/train_pipeline.py
```

Environment variable overrides:

| Variable | Default | Description |
|---|---|---|
| `SENTINEL_DATA_DIR` | `dataset/raw/ieee_cis` | IEEE-CIS data directory |
| `SENTINEL_MODEL_DIR` | `models/xgboost` | Model artifact directory |
| `SENTINEL_SAMPLE_FRAC` | (full) | Float in (0,1] to subsample for speed |

## Preprocessing

1. Numeric columns: median imputation.
2. Categorical columns: constant `MISSING` imputation + OrdinalEncoder (unknown → -1).
3. Pipeline fitted **on training split only**.
4. Reused identically at inference time.
5. Reusable by the future Isolation Forest implementation.

## Class Imbalance

Handled via `scale_pos_weight = n_negative / n_positive` in XGBClassifier.
No resampling applied.

On the 15% sample: scale_pos_weight = 27.11 (68,343 negatives / 2,521 positives).

## Splits

| Split | Fraction | Purpose |
|---|---|---|
| Train | 80% | Model fitting |
| Validation | 10% | Early stopping and model selection |
| Test | 10% | Final held-out evaluation (used once) |

Stratified by `isFraud` to preserve fraud rate across splits.

## Hyperparameters

See `models/xgboost/v1/metadata.json` for full hyperparameter record.

Key defaults:

- `objective`: `binary:logistic`
- `eval_metric`: `aucpr` (PR-AUC — best for imbalanced fraud data)
- `n_estimators`: 500
- `max_depth`: 6
- `learning_rate`: 0.05
- `early_stopping_rounds`: 30 (monitors validation PR-AUC)
- `tree_method`: `hist` (CPU-efficient)

## Artifacts

Saved to `models/xgboost/v1/` (gitignored):

| File | Contents |
|---|---|
| `preprocessor.joblib` | Fitted sklearn Pipeline |
| `xgb_model.joblib` | Fitted XGBClassifier |
| `feature_names.joblib` | Ordered feature name list |
| `metadata.json` | Version, timestamp, hyperparams, data stats |
| `evaluation_val.json` | Validation set metrics |
| `evaluation_test.json` | Test set metrics (final) |
| `shap_global_importance.csv` | Top features by mean \|SHAP\| |

## Classification Threshold

Default: **0.5**

This is documented in `metadata.json`. The threshold can be adjusted on
validation data to meet operational precision/recall requirements without
retraining.

## SHAP Explainability

- Global importance: mean |SHAP| across a random sample of training rows.
- Per-prediction: individual SHAP values showing feature direction and magnitude.
- SHAP values describe model behaviour. They are **not proof of fraud**.

## Inference Interface

```python
from src.ml.predictor import FraudPredictor

predictor = FraudPredictor()  # loads artifacts once at startup
result = predictor.predict_transaction({"TransactionAmt": 250.0, "ProductCD": "W", ...})
# result["fraud_probability"], result["is_fraud_predicted"], result["note"]
```

The predictor accepts a CanonicalTransaction-compatible dict via a documented
feature-mapping layer (future work for Agent 1 integration).

## Separation of Concerns

- Training is separate from inference.
- Artifacts are loaded once at startup; the model is never retrained on application start.
- The predictor is the only inference entry point.

## Testing

61 unit tests covering all modules. Run with:

```
.venv/bin/python -m pytest tests/ -v
```

All tests use small synthetic fixtures; they do not require the IEEE-CIS dataset.
