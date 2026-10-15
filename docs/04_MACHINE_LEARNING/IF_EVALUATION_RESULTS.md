# FILE: docs/04_MACHINE_LEARNING/IF_EVALUATION_RESULTS.md

# Isolation Forest — Evaluation Results

## Important Principles

* All metrics in this document are generated from **actual evaluation runs**.
* Isolation Forest is UNSUPERVISED. Metrics measure the correlation between
  statistical anomaly and the fraud label. They are NOT proof that IF
  independently detects fraud.
* ROC-AUC and PR-AUC are the meaningful metrics here — they are
  threshold-independent. Precision/Recall/F1 depend heavily on the threshold.

---

## Run — 15% IEEE-CIS Sample

**Run date:** 2026-10-14
**Dataset:** IEEE-CIS Fraud Detection — 15% stratified sample (88,581 rows)
**Split:** Stratified 90/10 train/test
**Default threshold:** 0.0 (model's natural decision boundary)

### Training Data Summary

| Metric | Value |
|---|---|
| Total rows (sampled) | 88,581 |
| Train rows | 79,722 |
| Test rows | 8,859 |
| Fraud base rate | 3.557% |
| n_estimators | 200 |
| contamination | auto |
| max_samples | auto |

### Anomaly Score Statistics (training set)

| Stat | Value |
|---|---|
| Mean anomaly score | 0.3540 |
| Std dev | 0.0512 |
| Min | 0.3115 |
| Max | 0.7403 |

Note: All training scores > 0.0, which means at threshold=0.0 the model
flags **every** transaction as anomalous. This is a property of the
contamination='auto' setting on this dataset and means the default threshold
of 0.0 is not operationally useful — see threshold discussion below.

### Held-Out Test Set Metrics (at default threshold = 0.0)

| Metric | Value | Note |
|---|---|---|
| Precision | 0.0356 | Equal to base fraud rate — all flagged |
| Recall | 1.0000 | All fraud caught — but all legit also flagged |
| F1-score | 0.0687 | Very low — threshold is not operational |
| **ROC-AUC** | **0.8036** | **Primary metric — threshold-independent** |
| **PR-AUC** | **0.1784** | **Primary metric — threshold-independent** |
| False Positive Rate | 1.0000 | All legitimate transactions flagged at threshold=0.0 |
| False Negative Rate | 0.0000 | All fraud caught (trivially, since all rows flagged) |

Confusion matrix (threshold=0.0):

|  | Pred-Legit | Pred-Anomaly |
|---|---|---|
| **Act-Legit (8,544)** | 0 | 8,544 |
| **Act-Fraud (315)** | 0 | 315 |

### Interpretation

> **The threshold=0.0 result is not a failure of the model — it reflects
> a calibration issue: at this threshold, every transaction scores above 0.**

The operationally relevant metrics are:

- **ROC-AUC = 0.8036**: The model has meaningful discriminative ability.
  A random detector would score 0.5. This is significantly above random.
- **PR-AUC = 0.1784**: On a 3.5% fraud base rate, random would score ~0.035.
  This is **~5× better than random**, showing real correlation between
  anomaly scores and fraud labels.

### Threshold Calibration (Phase 3 Completed)

In Phase 3, threshold calibration was executed using `scripts/run_threshold_calibration.py`.
Candidate thresholds were swept across [p90, p99] on a held-out calibration split (10% of training data with labels, held out from IF training).

**Calibrated Operating Point:**
- **Selected Threshold:** **0.4679** (F1-optimal on validation/calibration split; evaluated ONCE on held-out test set)

| Metric | Trivial Baseline (0.00) | Calibrated (**0.4679**) | Operational Impact |
|---|---|---|---|
| Precision | 0.0356 | **0.2618** | Increased from base fraud rate to ~26% |
| Recall | 1.0000 | **0.3333** | Catches 33.3% of fraud without supervised labels |
| F1-score | 0.0687 | **0.2933** | +326% relative improvement |
| False Positive Rate (FPR) | 1.0000 | **0.034644** | False alarms cut from 100% to **3.5%** |
| False Negative Rate (FNR) | 0.0000 | **0.666667** | Expected for unsupervised statistical model |
| Accuracy | 0.0356 | **0.9315** | Drastic reduction in false positive flags |
| ROC-AUC | 0.8036 | **0.8036** | Unchanged (threshold-independent) |
| PR-AUC | 0.1784 | **0.1784** | Unchanged (threshold-independent) |

Confusion matrix (test, threshold=0.4679):

|  | Pred-Legit | Pred-Anomaly |
|---|---|---|
| **Act-Legit (8,544)** | 8,248 | 296 |
| **Act-Fraud (315)** | 210 | 105 |

### Comparison with XGBoost (at respective calibrated thresholds)

| Metric | XGBoost (threshold=0.80) | IF (threshold=0.4679) |
|---|---|---|
| PR-AUC | 0.6620 | 0.1784 (~5× random) |
| ROC-AUC | 0.9342 | 0.8036 |
| Precision | 0.7143 | 0.2618 |
| Recall | 0.5397 | 0.3333 |
| F1-score | 0.6148 | 0.2933 |
| False Positive Rate | 0.0080 | 0.0346 |
| Nature | Supervised | Unsupervised |
| Interpretation | Fraud probability | Statistical anomaly score |

XGBoost significantly outperforms IF as an isolated fraud detector because it
is trained directly on fraud labels. IF's value is as an **unsupervised
cross-check**: it surfaces statistically unusual transactions without requiring historical fraud labels.

### Artifact Consistency Check

Score reload consistency: **max_diff = 0.00e+00 ✓** (bit-identical)

### Verified Limitations & Sample Distinction

1. **15% sample**: Evaluated on 15% IEEE-CIS sample (88,581 transactions). Full-dataset training (590k transactions) requires $\ge 16\text{GB}$ RAM and is supported in software.
2. **contamination='auto'**: This setting causes uncalibrated raw scores to exceed 0.0, necessitating the calibrated 0.4679 threshold.
3. **Anomaly ≠ Fraud**: Isolation Forest is an anomaly detector whose scores correlate with fraud labels. It must never be presented as an independent fraud probability.
