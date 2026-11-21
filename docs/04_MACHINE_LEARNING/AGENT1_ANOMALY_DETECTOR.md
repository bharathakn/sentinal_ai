# FILE: docs/04_MACHINE_LEARNING/AGENT1_ANOMALY_DETECTOR.md

# Agent 1 Anomaly Detector — Phase 4 Implementation

## Overview

Phase 4 implements the complete Agent 1 (Anomaly Detector) investigation node.
This document describes the implementation, score semantics, feature compatibility,
and operational behavior.

For the full architecture description, see `docs/02_AGENTS/AGENT_1_ANOMALY_DETECTOR.md`.

---

## Implementation Files

| File | Purpose |
|------|---------|
| `src/agents/agent1/anomaly_detector.py` | `AnomalyDetectorAgent` — full processing flow |
| `src/agents/agent1/output_schema.py` | `Agent1Output` Pydantic schema and sub-models |
| `src/agents/agent1/__init__.py` | Package exports |
| `src/agents/__init__.py` | Agents package init |
| `tests/test_agent1_anomaly_detector.py` | 54 tests covering all 5 required scenarios |

---

## Processing Flow

```
CanonicalTransaction (validated Pydantic model)
  │
  ├─ canonical_to_xgb_features()        [src/ml/feature_mapper.py]
  │   Returns sparse dict: 5 fields populated, 427 NaN
  │
  ├─ FraudPredictor.predict_transaction()  [src/ml/predictor.py]
  │   Returns: fraud_probability ∈ [0, 1], is_fraud_predicted, threshold_used
  │
  ├─ explain_prediction()                [src/ml/explainer.py]
  │   Returns: top_contributors (feature, shap_value, direction), base_value, shap_sum
  │
  ├─ canonical_to_if_features()          [src/ml/feature_mapper.py]
  │   Same output as canonical_to_xgb_features (shared feature space)
  │
  ├─ AnomalyPredictor.score_transaction()  [src/ml/if_predictor.py]
  │   Returns: anomaly_score ∈ ℝ, is_anomaly, threshold_used
  │
  ├─ _compute_combined_confidence()      [src/agents/agent1/anomaly_detector.py]
  │   Returns: float ∈ [0, 1] or None
  │
  └─ Agent1Output                        [src/agents/agent1/output_schema.py]
      Frozen Pydantic model, 20+ typed fields
```

---

## Score Semantics

### `anomaly_score` (= XGBoost `fraud_probability`)

| Property | Value |
|----------|-------|
| Source | XGBoost `binary:logistic` output |
| Range | [0, 1] |
| Meaning | Supervised probability-like score. Higher = model considers more fraud-like. |
| Model version | `1` |
| Calibrated threshold | `0.80` |
| **NOT** | A proven probability of fraud |

### `isolation_score` (= IF `-score_samples()`)

| Property | Value |
|----------|-------|
| Source | `-IsolationForest.score_samples()` |
| Range | ℝ (typically roughly -0.5 to 0.5 on this dataset) |
| Meaning | Unsupervised anomaly score. Higher = statistically more unusual. |
| Model version | `1` |
| Calibrated threshold | `0.4679` |
| **NOT** | A fraud probability. Cannot be directly compared to `anomaly_score`. |

### `combined_confidence`

| Property | Value |
|----------|-------|
| Range | [0, 1] or None |
| Formula | `0.70 × xgb_fraud_probability + 0.30 × sigmoid_normalise(isolation_score)` |
| Sigmoid centre | Calibrated IF threshold = `0.4679` |
| Sigmoid scale | `k = 5` |
| XGBoost weight | `0.70` (configurable) |
| IF weight | `0.30` (configurable) |
| Weight rationale | XGBoost PR-AUC=0.662 vs IF PR-AUC=0.178; higher weight for more precise model |
| **NOT** | A calibrated fraud probability |
| Unavailable when | Either model score is None |

**Sigmoid normalisation formula:**
```
sigmoid_if = 1 / (1 + exp(-5 × (isolation_score - 0.4679)))
```
- `isolation_score = 0.4679` → `sigmoid_if = 0.5`
- `isolation_score > 0.4679` → `sigmoid_if > 0.5` (above anomaly threshold)
- `isolation_score < 0.4679` → `sigmoid_if < 0.5` (below anomaly threshold)

**Combination:**
```
combined_confidence = 0.70 × fraud_probability + 0.30 × sigmoid_if
```

This does NOT fit any parameter on the test set.

---

## India-native scoring (Phase 9.5)

`INDIA_SYNTHETIC` transactions are scored by the India behavioural model
(`ScoringMode.INDIA_NATIVE`, 12 features, status COMPLETE when all features
and SHAP are available). See `INDIA_BEHAVIOUR_MODEL.md`. The IEEE-CIS
low-coverage limitation below applies only to non-India, non-IEEE-CIS input
or when the India model artifacts are missing (fallback with a warning).

## Feature Compatibility

### Mapped Features (5 of 432)

| Canonical Field | IEEE-CIS Column | Always Available? |
|----------------|-----------------|-------------------|
| `transaction.amount` | `TransactionAmt` | Yes |
| `transaction.sender.bank_name` | `card4` | No (optional) |
| `transaction.location.zip_code / region_code` | `addr1` | No (optional) |
| `transaction.sender.email_domain` | `P_emaildomain` | No (optional) |
| `transaction.receiver.email_domain` | `R_emaildomain` | No (optional) |

### Consequence

427 of 432 model features are NaN-imputed for a typical canonical transaction.
The model operates on imputed values for the vast majority of its features.

**Impact on scores:**
- Scores are genuine model outputs (not fabricated).
- Accuracy is substantially lower than IEEE-CIS benchmarks (PR-AUC=0.662 for full features).
- All canonical-mapped results carry `status = COMPATIBILITY_WARNING`.
- `warnings` always contains a NaN-imputation warning.

**Design decision:**
The canonical schema does not and should not be extended with 432 IEEE-CIS columns just to satisfy the model. The limitation is documented and surfaced to the caller. A future improvement could add an IEEE-CIS-native scoring path alongside the canonical path.

---

## Validation and Error Handling

### Input Validation

`CanonicalTransaction` is a frozen Pydantic model with strict validators:
- `raw_record_id` must not be empty.
- `amount` must be >= 0.
- `currency` must be exactly 3 characters.
- `latitude` must be in [-90, 90]; `longitude` in [-180, 180].

Validation failures raise `pydantic.ValidationError` before any model code is reached.

### Model Loading

`AnomalyDetectorAgent.__init__` loads both models at construction time.
- A missing artifact raises `FileNotFoundError` with a clear message.
- This is intentional fail-fast behavior: a missing artifact is a configuration error.

### Runtime Inference Failures

If `predict_transaction()` or `score_transaction()` raises after init:
- The relevant score becomes `None`.
- The error is appended to `Agent1Output.errors`.
- `combined_confidence` becomes `None`.
- `status` is set to `PARTIAL` (one model) or `FAILED` (both models).
- The agent does NOT silently substitute `0.0` or any other value.

### SHAP Failures

If the SHAP computation fails:
- `shap_available = False`
- `top_deviation_features = []`
- A warning is appended to `Agent1Output.warnings`
- The model scores are still returned (SHAP is non-critical).

---

## Model Artifacts

Both trained models are present at:
- `models/xgboost/v1/` — XGBoost model, preprocessor, feature names, metadata, threshold
- `models/isolation_forest/v1/` — IF model, preprocessor, feature names, metadata, threshold

Training was performed on a **15% stratified IEEE-CIS sample** (70,864 training rows).
Full-dataset training requires ≥16 GB available RAM — the current development host has ~14 GB total.

---

## Test Results (Phase 4)

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_agent1_anomaly_detector.py` | 54 | All pass |
| `tests/test_agent1_scorer.py` | 10 | All pass (Phase 3 tests preserved) |
| Full suite | 319 | All pass |

### Test Scenario Coverage

| Scenario | Tests | Description |
|----------|-------|-------------|
| Normal transaction | 13 | Valid input, complete output, types, provenance |
| Suspicious transaction | 6 | High-risk characteristics, combination strategy |
| Malformed transaction | 8 | Pydantic rejects bad input; no inference reached |
| Missing feature | 8 | Canonical mapping limitation; NaN coverage; None vs 0.0 |
| Model unavailable | 10 | Fail-fast init; inference failures; zero-score prevention |
| score_raw integration | 2 | Raw IEEE-CIS feature dict scoring |
| combined_confidence unit | 7 | Sigmoid, determinism, range, weights |

---

## How to Invoke Agent 1

```python
from src.agents.agent1 import AnomalyDetectorAgent
from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter

# Load models once at startup
agent = AnomalyDetectorAgent()

# Build canonical transaction from an IEEE-CIS row
raw_row = {
    "TransactionID": 2987000,
    "TransactionAmt": 150.0,
    "ProductCD": "W",
    "card4": "visa",
    "P_emaildomain": "gmail.com",
}
tx = IEEECISAdapter.from_row(raw_row)

# Score
result = agent.score(tx)

# Inspect
print(result.status)                    # COMPATIBILITY_WARNING
print(result.anomaly_score)             # e.g. 0.385 (XGBoost fraud probability)
print(result.isolation_score)           # e.g. 0.316 (IF anomaly score)
print(result.combined_confidence)       # e.g. 0.365 (heuristic composite)
print(result.shap_available)            # True
print(len(result.top_deviation_features))  # 10
for feat in result.top_deviation_features[:3]:
    print(feat.feature, feat.shap_value, feat.direction)
```

---

## Known Limitations and Remaining Work

1. **Feature coverage**: Only 5/432 IEEE-CIS features can be mapped from canonical transactions. This fundamentally limits model accuracy for canonical inputs.
2. **LangGraph wiring**: `AnomalyDetectorAgent` is LangGraph-ready but not yet wired. LangGraph is not installed.
3. **combined_confidence calibration**: The 70/30 weighting is heuristically motivated, not cross-validated. Formal calibration would require held-out data and a defined cost function.
4. **Full-dataset training**: Model artifacts are from a 15% sample due to host RAM constraints. Full-dataset training is supported by the training scripts but has not been run on the current host.
5. **Deviation-from-population analysis**: `top_deviation_features` currently reflects SHAP attribution (model reasoning), not statistically measured deviation from a reference population. True deviation analysis would require a baseline distribution.
