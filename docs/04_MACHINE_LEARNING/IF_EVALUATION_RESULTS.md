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

### Threshold Recommendation

The anomaly score distribution shows all values > 0.31 on training data.
The decision threshold should be raised to a high percentile of the
anomaly score distribution to achieve operational precision.

**Recommended next step:** Plot the score distribution on training data and
set the threshold at the 95th–99th percentile. For example, if the 95th
percentile of training scores is 0.40, set `threshold=0.40`. Evaluate
precision/recall trade-off on held-out validation data.

**Do not set the threshold by repeatedly evaluating against the test set.**

### Comparison with XGBoost (at their respective thresholds)

| Metric | XGBoost (threshold=0.5) | IF (threshold=0.0) |
|---|---|---|
| PR-AUC | 0.6620 | 0.1784 |
| ROC-AUC | 0.9342 | 0.8036 |
| Nature | Supervised | Unsupervised |
| Interpretation | Fraud probability | Anomaly score |

XGBoost significantly outperforms IF as an isolated fraud detector because it
is trained directly on fraud labels. IF's value is as an **unsupervised
cross-check**: it can surface unusual transactions not seen in historical fraud
patterns.

### Artifact Consistency Check

Score reload consistency: **max_diff = 0.00e+00 ✓** (bit-identical)

### Remaining Limitations

1. **Threshold calibration required**: Default threshold=0.0 is not operational.
   Calibrate on validation data before deployment.
2. **15% sample**: Full-dataset training may produce different score distributions.
3. **contamination='auto'**: This setting produces a model where all scores on
   this dataset exceed 0.0. Explicitly setting contamination (e.g. 0.05) would
   shift the threshold but would require careful justification.
4. **Anomaly ≠ Fraud**: The model is not a fraud detector. It is an anomaly
   detector whose scores correlate with fraud labels.
