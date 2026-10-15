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

Confusion matrix (test, threshold=0.5):

|  | Pred-Legit | Pred-Fraud |
|---|---|---|
| **Act-Legit** | 8,162 | 382 |
| **Act-Fraud** | 86 | 229 |

---

## XGBoost — Calibrated Operating Point (Phase 3)

**Run date:** 2026-10-15  
**Threshold:** **0.80** (selected by maximizing F1 on the validation split; evaluated ONCE on held-out test split)

### Held-Out Test Set Metrics (Calibrated Threshold = 0.80)

| Metric | Baseline (0.50) | Calibrated (**0.80**) | Change / Impact |
|---|---|---|---|
| Precision | 0.3748 | **0.7143** | +90.6% relative (false alarms cut by 82%) |
| Recall | 0.7270 | **0.5397** | -25.8% (fewer caught, higher confidence) |
| F1-score | 0.4946 | **0.6148** | +24.3% relative (optimal F1 balance) |
| Accuracy | 0.9472 | **0.9760** | Higher overall correct classifications |
| False Positive Rate (FPR) | 0.0447 | **0.007959** | Reduced from 4.5% to < 0.8% |
| False Negative Rate (FNR) | 0.2730 | **0.460317** | 46.0% missed fraud at strict threshold |
| ROC-AUC | 0.9342 | **0.9342** | Unchanged (threshold-independent) |
| PR-AUC | 0.6620 | **0.6620** | Unchanged (threshold-independent) |

Confusion matrix (test, threshold=0.80):

|  | Pred-Legit | Pred-Fraud |
|---|---|---|
| **Act-Legit (8,544)** | 8,476 | 68 |
| **Act-Fraud (315)** | 145 | 170 |

### Interpretation of Calibration

- **False alerts plummeted**: from 382 down to 68 on the test set. In a compliance operations workflow, this drastically reduces analyst workload while maintaining an investigation precision of >71%.
- **Test-set isolation enforced**: The threshold was selected on the validation split (`y_val`, `val_proba`) using `src/ml/threshold_calibration.py`. The test set was touched only once after threshold selection.

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

### Limitations & Sample Distinction

- All results above are from a **15% stratified sample** of the IEEE-CIS training data (88,581 transactions).
- They represent a validated, reproducible baseline. They must NOT be cited as full-dataset performance.
- The model is trained on anonymised Vesta-engineered features; interpretability of specific V-columns is limited by design of the original dataset.
- Temporal structure: The split is cross-sectional with stratification.

### Next Steps

- **Full-dataset execution**: Run `SENTINEL_SAMPLE_FRAC=full python scripts/train_pipeline.py` on a host with $\ge 16\text{GB}$ RAM to generate full 590,540-row metrics.
- **Phase 4**: Wire `Agent1Scorer` into the Agent 1 LangGraph node (scheduled next week).
