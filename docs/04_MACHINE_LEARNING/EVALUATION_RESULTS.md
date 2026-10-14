# FILE: docs/04_MACHINE_LEARNING/EVALUATION_RESULTS.md

# ML Evaluation Results

## Important Principle

All metrics in this document are generated from **actual evaluation runs**.
Planned target values and measured results are explicitly distinguished.

---

## XGBoost — Initial Run (15% IEEE-CIS Sample)

**Run date:** 2026-10-14
**Dataset:** IEEE-CIS Fraud Detection — 15% stratified sample (88,581 rows)
**Split:** Stratified 80/10/10 train/val/test
**Threshold:** 0.5 (default)

### Training Data Summary

| Metric | Value |
|---|---|
| Total rows (sampled) | 88,581 |
| Train rows | 70,864 |
| Validation rows | 8,858 |
| Test rows | 8,859 |
| Fraud base rate | 3.557% |
| Positives (train) | 2,521 |
| Negatives (train) | 68,343 |
| scale_pos_weight | 27.11 |
| Features | 432 (401 numeric + 31 categorical) |
| Best XGBoost iteration | 499 |

### Validation Set Metrics (used for model selection only)

| Metric | Value |
|---|---|
| Precision | 0.3604 |
| Recall | 0.7460 |
| F1-score | 0.4860 |
| ROC-AUC | 0.9267 |
| **PR-AUC** | **0.6493** |

Confusion matrix (validation):

|  | Pred-Legit | Pred-Fraud |
|---|---|---|
| **Act-Legit** | 8,126 | 417 |
| **Act-Fraud** | 80 | 235 |

### Held-Out Test Set Metrics (final evaluation — used once)

| Metric | Value |
|---|---|
| Precision | 0.3748 |
| Recall | 0.7270 |
| F1-score | 0.4946 |
| ROC-AUC | 0.9342 |
| **PR-AUC** | **0.6620** |

Confusion matrix (test):

|  | Pred-Legit | Pred-Fraud |
|---|---|---|
| **Act-Legit** | 8,162 | 382 |
| **Act-Fraud** | 86 | 229 |

### Interpretation

- **ROC-AUC 0.934**: Very strong discrimination between fraud and legitimate transactions.
- **PR-AUC 0.662**: Meaningful detection on a severely imbalanced dataset (base rate ~3.5%).
  A random classifier would achieve PR-AUC ≈ 0.035. This is ~19× better than random.
- **Recall 0.727**: The model catches ~73% of actual fraud cases at the default threshold.
- **Precision 0.375**: ~38% of flagged transactions are actual fraud at the default threshold.
  This is expected at a 0.5 threshold with high class imbalance; threshold adjustment can
  trade recall for precision based on operational requirements.
- **Accuracy is not reported as the primary metric.** A trivial all-zeros classifier would
  achieve ~96.4% accuracy on this dataset. That is meaningless for fraud detection.

### Top 10 Features by Mean |SHAP|

| Rank | Feature | Mean |SHAP| |
|---|---|---|
| 1 | TransactionAmt | 0.2251 |
| 2 | card6 | 0.2147 |
| 3 | C1 | 0.2102 |
| 4 | card1 | 0.2035 |
| 5 | R_emaildomain | 0.1778 |
| 6 | TransactionDT | 0.1753 |
| 7 | C13 | 0.1744 |
| 8 | V91 | 0.1688 |
| 9 | card2 | 0.1613 |
| 10 | C14 | 0.1529 |

SHAP values describe model feature attribution. They are not proof that any
individual feature makes a transaction fraudulent.

### Artifact Consistency Check

Predictions reloaded from saved artifacts: **max_diff = 0.00e+00 ✓**
(Bit-identical predictions before and after serialisation.)

### Limitations

- Results are from a **15% sample** of the full IEEE-CIS training data for a
  rapid initial verification. Full-dataset training is expected to improve metrics.
- Threshold of 0.5 is the default; operational threshold should be tuned on the
  validation set according to the institution's precision/recall requirements.
- The model is trained on anonymised Vesta-engineered features; interpretability
  of specific V-columns is limited by design of the original dataset.
- No temporal cross-validation has been performed; the split is cross-sectional.

### Next Steps

- Run `scripts/train_pipeline.py` without `SENTINEL_SAMPLE_FRAC` for full-dataset metrics.
- Tune classification threshold on validation set.
- Implement Isolation Forest for unsupervised cross-check (Phase 2).
