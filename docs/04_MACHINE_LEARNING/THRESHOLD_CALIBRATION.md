# FILE: docs/04_MACHINE_LEARNING/THRESHOLD_CALIBRATION.md

# Threshold Calibration

## Status

**IMPLEMENTED AND VERIFIED** — Phase 3

## Purpose

Classification thresholds control the trade-off between precision (fewer false alarms) and
recall (fewer missed fraud cases). The optimal threshold depends on the operational cost of
each error type. Where no business cost function is available, F1-maximisation is used as a
defensible default.

> **Rule**: Threshold selection uses the VALIDATION split only. The test set is evaluated
> once after selection and never again to avoid information leakage.

## Module

`src/ml/threshold_calibration.py`

**Functions:**

| Function | Purpose |
|---|---|
| `sweep_thresholds(y, scores, ...)` | Evaluate a list of candidate thresholds on validation data |
| `select_threshold(sweep_df, objective)` | Pick the best threshold by objective |
| `save_threshold_report(result, path)` | Persist selected threshold metadata to JSON |
| `print_sweep_summary(df)` | Print human-readable sweep table |

**Objectives:** `f1` (default), `precision`, `recall`, `balanced_f1`

`sweep_thresholds()` raises `ValueError` if `dataset_label='test'` — enforces test-set isolation.

## XGBoost Threshold Calibration

**Run date:** 2026-10-15
**Dataset:** IEEE-CIS — 15% stratified sample (88,581 rows)
**Split:** 80/10/10 stratified train/val/test

### Baseline (threshold = 0.5)

| Metric | Value |
|---|---|
| Precision | 0.3748 |
| Recall | 0.7270 |
| F1-score | 0.4946 |
| Accuracy | *not reported at baseline* |
| FPR | *not reported at baseline* |
| FNR | *not reported at baseline* |
| ROC-AUC | 0.9342 |
| PR-AUC | 0.6620 |

Confusion matrix (TN=8162, FP=382, FN=86, TP=229).

### Selected threshold = 0.80 (F1-optimal on validation)

| Metric | Validation | Test (held-out, evaluated ONCE) |
|---|---|---|
| Precision | ~0.69 | **0.7143** |
| Recall | ~0.55 | **0.5397** |
| F1-score | ~0.61 | **0.6148** |
| Accuracy | — | **0.9760** |
| FPR | — | **0.007959** |
| FNR | — | **0.460317** |
| ROC-AUC | unchanged (0.9342) | **0.9342** |
| PR-AUC | unchanged (0.6620) | **0.6620** |

Confusion matrix (test): TN=8476, FP=68, FN=145, TP=170.

### Interpretation

Raising the threshold from 0.5 to 0.8:
- **Precision improves**: 0.375 → 0.714 (fewer false alarms)
- **Recall decreases**: 0.727 → 0.540 (more missed fraud)
- **F1 improves**: 0.495 → 0.615 (better balance)
- **FPR drops**: 382 false positives → 68

The calibrated threshold is more suitable for an investigation pipeline where each false
alarm has a cost. An operator may choose a lower threshold (more recalls, more false alarms)
if the cost of missing fraud is higher than investigating false alarms.

> **ROC-AUC and PR-AUC are threshold-independent.** They do not change with threshold choice.
> They reflect the model's discriminative power across all thresholds.

### Artifacts

```
models/xgboost/v1/
  evaluation_test.json             — historical baseline (threshold=0.5)
  evaluation_val_calibrated.json   — calibrated validation metrics
  evaluation_test_calibrated.json  — final test metrics (calibrated threshold)
  threshold_calibration.json       — selected threshold + selection metadata
```

---

## Isolation Forest Threshold Calibration

**Run date:** 2026-10-15
**Dataset:** IEEE-CIS — 15% stratified sample
**Split:** 90/10 train/test (IF doesn't use early stopping); 10% of train used as calibration set

### Trivial operating point (threshold = 0.0)

All 8,859 transactions flagged as anomalous. FPR = 1.000, FNR = 0.000. Not operationally useful.

See `IF_EVALUATION_RESULTS.md` for the full discussion.

### Calibration methodology

Score distribution on the calibration set (10% of training data, labeled):

| Percentile | Score |
|---|---|
| p50 | 0.3356 |
| p90 | 0.4104 |
| p95 | 0.4619 |
| p99 | 0.5665 |

Candidate thresholds were swept over [p90, p99] = [0.4104, 0.5665] (20 points).

> Threshold calibration uses labeled validation data to SELECT the threshold.
> The IF model itself was NOT retrained and labels were NOT seen during `model.fit()`.
> This keeps the model unsupervised while using labels only for operational threshold selection.

### Selected threshold = 0.4679 (F1-optimal on calibration set)

| Metric | Calibration set | Test (held-out, evaluated ONCE) |
|---|---|---|
| Precision | 0.2439 | **0.2618** |
| Recall | 0.3169 | **0.3333** |
| F1-score | 0.2757 | **0.2933** |
| FPR | 0.0363 | **0.034644** |
| FNR | 0.683 | **0.666667** |
| ROC-AUC | unchanged (0.8036) | **0.8036** |
| PR-AUC | unchanged (0.1784) | **0.1784** |

Confusion matrix (test): TN=8248, FP=296, FN=210, TP=105.

### Interpretation

> Isolation Forest is **unsupervised**. It detects statistical anomalies, not fraud.
> The calibrated threshold improves operational usefulness (FPR drops from 100% to 3.5%)
> at the cost of catching only 33% of fraud. This is expected for an unsupervised model.

The IF model functions as a first-pass anomaly signal to route transactions for further
investigation. It should NOT be used as a standalone fraud detector.

> **Anomaly score ≠ Fraud probability.** Do NOT sum or compare directly with XGBoost output.

### Artifacts

```
models/isolation_forest/v1/
  evaluation_test.json             — trivial baseline (threshold=0.0)
  evaluation_test_calibrated.json  — final test metrics (calibrated threshold)
  threshold_calibration.json       — selected threshold + selection metadata
```

---

## Comparison Summary

| Model | Threshold | Precision | Recall | F1 | FPR | FNR | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|---|
| XGBoost (baseline) | 0.5 | 0.375 | 0.727 | 0.495 | 0.045 | 0.273 | 0.934 | 0.662 |
| **XGBoost (calibrated)** | **0.8** | **0.714** | **0.540** | **0.615** | **0.008** | **0.460** | **0.934** | **0.662** |
| IF (trivial) | 0.0 | 0.036 | 1.000 | 0.069 | 1.000 | 0.000 | 0.804 | 0.178 |
| **IF (calibrated)** | **0.468** | **0.262** | **0.333** | **0.293** | **0.035** | **0.667** | **0.804** | **0.178** |

Note: All results are from a 15% IEEE-CIS sample. Full-dataset results may differ.

## Reproduction

```bash
# Requires trained model artifacts in models/
python scripts/run_threshold_calibration.py
```

To train from scratch first:

```bash
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_pipeline.py
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_isolation_forest.py
python scripts/run_threshold_calibration.py
```
