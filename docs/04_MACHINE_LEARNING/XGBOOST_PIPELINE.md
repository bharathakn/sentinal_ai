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

1. Numeric columns: median imputation (`SimpleImputer(strategy='median')`).
2. Categorical columns: constant `MISSING` imputation + `OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)`.
3. Pipeline fitted **on training split only** (`build_preprocessing_pipeline()`).
4. Reused identically at inference time.
5. Reused directly by the Isolation Forest implementation.

## Class Imbalance

Handled via `scale_pos_weight = n_negative / n_positive` in XGBClassifier.
No resampling applied.

On the 15% sample: scale_pos_weight = 27.11 (68,343 negatives / 2,521 positives).

## Splits

| Split | Fraction | Purpose |
|---|---|---|
| Train | 80% | Model fitting |
| Validation | 10% | Early stopping, hyperparameter check, and threshold calibration |
| Test | 10% | Final held-out evaluation (evaluated once) |

Stratified by `isFraud` to preserve fraud rate across splits.

## Hyperparameters

See `models/xgboost/v1/metadata.json` for full hyperparameter record.

Key defaults:

- `objective`: `binary:logistic`
- `eval_metric`: `aucpr` (PR-AUC — primary metric for imbalanced fraud data)
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
| `evaluation_val.json` | Baseline validation set metrics (threshold=0.5) |
| `evaluation_test.json` | Baseline test set metrics (threshold=0.5) |
| `evaluation_val_calibrated.json` | Calibrated validation metrics (threshold=0.8) |
| `evaluation_test_calibrated.json` | Calibrated test metrics (threshold=0.8) |
| `threshold_calibration.json` | Selected threshold metadata and optimization objective |
| `shap_global_importance.csv` | Top features by mean \|SHAP\| |

## Classification Thresholds

- **Baseline Threshold**: `0.5` (default). Precision=0.3748, Recall=0.7270, F1=0.4946.
- **Calibrated Threshold**: `0.80` (selected via F1-maximization on validation set). Precision=0.7143, Recall=0.5397, F1=0.6148, FPR=0.0080, Accuracy=0.9760.
- Calibration script: `scripts/run_threshold_calibration.py`.
- Full details: `THRESHOLD_CALIBRATION.md`.

## SHAP Explainability

- Global importance: mean |SHAP| across sample of preprocessed rows (`src/ml/explainer.py`).
- Per-prediction: individual SHAP values showing feature direction and magnitude (`explain_prediction()`).
- SHAP values describe model behaviour. They are **not proof of fraud**.

## Inference & Feature Mapping Interface

```python
from src.ml.predictor import FraudPredictor
from src.ml.feature_mapper import canonical_to_xgb_features

predictor = FraudPredictor()  # loads artifacts once at startup, never retrains

# Inference from raw IEEE-CIS feature dict
result = predictor.predict_transaction({"TransactionAmt": 250.0, "ProductCD": "W", ...})
# result["fraud_probability"], result["is_fraud_predicted"], result["note"]

# Inference from CanonicalTransaction via feature mapper
features = canonical_to_xgb_features(canonical_tx)
result = predictor.predict_transaction(features)
```

## Separation of Concerns

- Training is separate from inference.
- Artifacts are loaded once at startup; the model is never retrained on application start.
- The predictor is the inference entry point; `Agent1Scorer` bundles both XGBoost and Isolation Forest signals for Agent 1.

## Testing & Verification

Automated tests covering the XGBoost pipeline, loader, preprocessor, predictor, evaluator, explainer, feature mapper, and threshold calibration:

```bash
.venv/bin/python -m pytest tests/test_trainer.py tests/test_predictor.py tests/test_evaluator.py tests/test_explainer.py tests/test_preprocessor.py tests/test_threshold_calibration.py tests/test_feature_mapper.py -v
```

Total project test suite: **265 tests passing** (`.venv/bin/python -m pytest tests/`).
