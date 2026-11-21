# FILE: docs/02_AGENTS/AGENT_1_ANOMALY_DETECTOR.md

# Agent 1 — Anomaly Detector

## Purpose

Determine how abnormal a financial transaction is relative to expected customer behavior using supervised and unsupervised machine learning models.

## Implementation Status

- **ML Inference Layer (Phases 2 & 3 — COMPLETE & VERIFIED)**:
  - Supervised fraud detection: XGBoost (`src/ml/trainer.py`, `src/ml/predictor.py`)
  - Unsupervised anomaly detection: Isolation Forest (`src/ml/if_trainer.py`, `src/ml/if_predictor.py`)
  - Feature mapping: `src/ml/feature_mapper.py` (CanonicalTransaction → model feature space)
  - Lower-level inference engine: `src/ml/agent1_scorer.py` (`Agent1Scorer`)
  - Explainability: SHAP (`src/ml/explainer.py`)
  - Threshold calibration: `src/ml/threshold_calibration.py` (XGBoost=0.80, IF=0.4679)
- **Agent 1 Node — Phase 4 COMPLETE**:
  - `src/agents/agent1/anomaly_detector.py` — `AnomalyDetectorAgent`
  - `src/agents/agent1/output_schema.py` — `Agent1Output` Pydantic schema
  - 54 new tests, all passing (`tests/test_agent1_anomaly_detector.py`)
  - `combined_confidence` fusion strategy implemented and documented
  - SHAP per-prediction explanations integrated
  - Structured `top_deviation_features` output
- **LangGraph Node Wiring — COMPLETE (Phase 12)**:
  - Runs as the `anomaly_detector` node (`src/agents/pipeline_graph.py`);
    see `docs/09_BACKEND/LANGGRAPH_PIPELINE.md`.

---

## Architecture

### Data Flow

```
CanonicalTransaction (Pydantic, validated)
  ↓ canonical_to_xgb_features()     [feature_mapper.py]
  ↓ FraudPredictor.predict_transaction()   [predictor.py]
  ↓ explain_prediction()             [explainer.py — SHAP]
  ↓ AnomalyPredictor.score_transaction()  [if_predictor.py]
  ↓ _compute_combined_confidence()   [anomaly_detector.py]
  ↓
Agent1Output (frozen Pydantic model)
```

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `src/agents/agent1/anomaly_detector.py` | Full Agent 1 flow; model loading; SHAP; combined_confidence |
| `src/agents/agent1/output_schema.py` | Pydantic output contract; field types; nullability rules |
| `src/ml/feature_mapper.py` | CanonicalTransaction → IEEE-CIS feature dict |
| `src/ml/predictor.py` | XGBoost inference wrapper |
| `src/ml/if_predictor.py` | Isolation Forest inference wrapper |
| `src/ml/explainer.py` | SHAP TreeExplainer (cached per model instance) |
| `src/ml/agent1_scorer.py` | Lower-level dict-based ML scoring (preserved from Phase 3) |

---

## Models

### Primary Model: XGBoost (Supervised)

- Objective: `binary:logistic`
- Output: `fraud_probability` ∈ [0, 1]
- Calibrated threshold: `0.80` (Precision=0.727, Recall=0.524, F1=0.609)
- Model version: `1` — artifacts at `models/xgboost/v1/`

### Secondary Model: Isolation Forest (Unsupervised)

- Detects statistical anomalies without using fraud labels during training.
- Output: `anomaly_score` = `-IsolationForest.score_samples()` ∈ ℝ (higher = more unusual; **NOT a probability**).
- Calibrated threshold: `0.4679` (used as sigmoid centre for `combined_confidence`)
- Model version: `1` — artifacts at `models/isolation_forest/v1/`
- Provides an independent cross-check on XGBoost.

---

## Output Schema (`Agent1Output`)

All fields are typed and documented. `None` is the sentinel for unavailable values; `0.0` is never used as a missing-score substitute.

| Field | Type | Description |
|-------|------|-------------|
| `transaction_id` | `str \| None` | `raw_record_id` from CanonicalTransaction |
| `source_dataset` | `str \| None` | `source_dataset` from CanonicalTransaction |
| `scored_at_utc` | `datetime` | UTC timestamp of scoring |
| `status` | `AgentStatus` | `COMPLETE`, `PARTIAL`, `FAILED`, `COMPATIBILITY_WARNING` |
| `warnings` | `list[str]` | Non-fatal warnings (e.g. low feature coverage) |
| `errors` | `list[str]` | Component error messages |
| `anomaly_score` | `float \| None` | XGBoost `fraud_probability` ∈ [0, 1] |
| `isolation_score` | `float \| None` | IF anomaly score ∈ ℝ (higher = more anomalous) |
| `combined_confidence` | `float \| None` | Heuristic fusion ∈ [0, 1]; see below |
| `top_deviation_features` | `list[DeviationFeature]` | SHAP attributions, ranked |
| `xgboost_detail` | `XGBoostDetail \| None` | Full XGBoost result |
| `isolation_forest_detail` | `IsolationForestDetail \| None` | Full IF result |
| `shap_available` | `bool` | Whether SHAP succeeded |
| `shap_base_value` | `float \| None` | SHAP expected value (base log-odds) |
| `shap_sum` | `float \| None` | Sum of SHAP values (log-odds shift) |
| `feature_mapping` | `FeatureMappingInfo \| None` | Feature coverage summary |
| `combined_confidence_note` | `str` | Documents combination strategy |

---

## Score Semantics

### `anomaly_score`

XGBoost `fraud_probability` ∈ [0, 1]. Supervised probability from `binary:logistic` model.
This is a statistical signal, not proof of fraud.

### `isolation_score`

Isolation Forest `-score_samples()` ∈ ℝ. Higher = more statistically unusual.
**NOT a probability.** Scale differs from `anomaly_score`. Cannot be directly compared.

### `combined_confidence`

Heuristic composite of both model signals. **NOT a calibrated fraud probability.**

**Strategy:**
1. XGBoost component: `fraud_probability` directly (weight = 0.70).
2. IF component: sigmoid-normalised `anomaly_score` centred on calibrated IF threshold `0.4679` (weight = 0.30).
   - `sigmoid_if = 1 / (1 + exp(-5 × (anomaly_score - 0.4679)))`
   - Maps IF score to [0, 1] monotonically.
3. `combined_confidence = 0.70 × xgb_prob + 0.30 × sigmoid_if`

**Rationale for weights:** XGBoost (PR-AUC=0.662) substantially outperforms IF (PR-AUC=0.178). The 70/30 weighting reflects this. Weights are configurable at agent construction.

**Limitations:**
- `combined_confidence` is `None` when either model is unavailable.
- Not fit on the test set (no parameter tuning).
- Not a calibrated probability — interpret as a relative ranking signal only.

### `top_deviation_features`

SHAP attributions for the XGBoost prediction, ranked by absolute SHAP value.
- `direction = "increases_fraud_score"` when `shap_value > 0`
- `direction = "decreases_fraud_score"` when `shap_value < 0`
- `feature_value = None` for NaN-imputed features
- SHAP attributes model reasoning, **not causal fraud intent**.

---

## Feature Mapping and Compatibility Limitation

The canonical transaction schema contains only a small subset of the 432 IEEE-CIS features the models were trained on.

| Canonical Field | IEEE-CIS Column | Notes |
|----------------|-----------------|-------|
| `amount` | `TransactionAmt` | Always mapped |
| `sender.bank_name` | `card4` | Optional |
| `location.zip_code / region_code` | `addr1` | Optional |
| `sender.email_domain` | `P_emaildomain` | Optional |
| `receiver.email_domain` | `R_emaildomain` | Optional |

**Consequence:** 427/432 features are NaN-imputed for a typical canonical transaction. The model operates mostly on imputed values. Accuracy is substantially lower than IEEE-CIS benchmarks (PR-AUC=0.662). Status is always `COMPATIBILITY_WARNING` when scoring canonical transactions.

Scores are genuine model outputs and are not fabricated. The limitation is explicitly reported in `feature_mapping.mapping_warning` and in `warnings`.

---

## Validation Behavior

| Input | Behavior |
|-------|----------|
| Valid CanonicalTransaction | Scored; warnings about feature coverage |
| Missing optional fields (e.g. no email domain) | Scored; those features NaN-imputed |
| Empty `raw_record_id` | Pydantic raises `ValidationError` before scoring |
| Negative amount | Pydantic raises `ValidationError` before scoring |
| Missing XGBoost artifact | `FileNotFoundError` raised at `AnomalyDetectorAgent.__init__`, unless `require_ieee_models=False` / `SENTINEL_REQUIRE_IEEE_MODELS=false` (hosted deployments): then the model is skipped and IEEE-CIS scoring returns a structured `FAILED` output |
| XGBoost inference failure | `anomaly_score = None`, error logged, status FAILED or PARTIAL |
| Missing IF artifact | Same as XGBoost |
| IF inference failure | `isolation_score = None`, error logged |
| SHAP failure | Warning logged; `shap_available = False`; `top_deviation_features = []` |
| Both models fail | `status = FAILED`; both scores `None`; `combined_confidence = None` |

---

## Usage

```python
from src.agents.agent1 import AnomalyDetectorAgent
from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter

# Load once at application startup
agent = AnomalyDetectorAgent()

# Score a canonical transaction
tx = IEEECISAdapter.from_row(raw_row)
result = agent.score(tx)

print(result.status)               # AgentStatus.COMPATIBILITY_WARNING
print(result.anomaly_score)        # XGBoost fraud_probability ∈ [0, 1]
print(result.isolation_score)      # IF anomaly_score (any float)
print(result.combined_confidence)  # Heuristic composite ∈ [0, 1]
print(result.top_deviation_features[:3])  # Top 3 SHAP attributions

# Score a raw IEEE-CIS feature dict (bypasses mapping)
result_raw = agent.score_raw({"TransactionAmt": 250.0, "card4": "visa"})
```

---

## Tests

All 54 Phase 4 Agent 1 tests are in `tests/test_agent1_anomaly_detector.py`.

| Test Class | Scenario |
|------------|----------|
| `TestNormalTransaction` | Valid canonical transaction; complete output verification |
| `TestSuspiciousTransaction` | High-risk characteristics; structure and combination strategy |
| `TestMalformedTransaction` | Pydantic validation rejects bad input before inference |
| `TestMissingFeature` | Canonical-to-IEEE-CIS limitation; NaN imputation; coverage warnings |
| `TestModelUnavailable` | Missing artifacts raise; inference failures return None gracefully |
| `TestScoreRaw` | Raw IEEE-CIS feature dict integration |
| `TestCombinedConfidenceUnit` | `combined_confidence` formula determinism and range |

Run with:
```bash
.venv/bin/python -m pytest tests/test_agent1_anomaly_detector.py -v
# Full suite:
.venv/bin/python -m pytest tests/ -v
```

---

## Handoff

The `Agent1Output` is a frozen Pydantic model intended for consumption by Agent 2 (Evidence Gatherer) and Agent 4 (Risk Assessor). When LangGraph is wired, `Agent1Output` will be written to `SentinelState["agent1_output"]`.

## Core Rules

- Use structured output (`Agent1Output`).
- Preserve model metadata and timestamps.
- Do not combine XGBoost probabilities and Isolation Forest scores without a validated fusion strategy.
- `combined_confidence` is a heuristic signal, not a calibrated probability.
- Treat generated AI output as untrusted until validated by the Output Validator.
- SHAP values describe model behavior, not causal fraud evidence.