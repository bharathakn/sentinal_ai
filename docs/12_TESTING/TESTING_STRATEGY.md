# FILE: docs/12_TESTING/TESTING_STRATEGY.md

# Testing Strategy

## Goal

Verify that Sentinel AI produces correct, traceable and validated investigation results.

## Current status (2026-11-22)

| Suite | Command | Count |
|---|---|---|
| Python (all phases) | `.venv/bin/python -m pytest tests/ -q` | ~1,090; live Neo4j / MongoDB tests run when `.env` has credentials |
| Dashboard | `cd frontend && npm test` | 15 (Vitest + Testing Library) |

The inventory below is the Phase 1–3 snapshot. Later suites are named after
their component, e.g. `tests/test_pipeline_graph.py`, `tests/test_api.py`,
`tests/test_auth.py` and `tests/test_network_view.py`.

## Testing Layers

### Unit Tests (Phases 1–3 Verified)

The project currently has **265 automated tests** passing in ~12 seconds:

```bash
.venv/bin/python -m pytest tests/ -v
```

#### Test Suite Inventory

| Test File | Count | Scope & Focus |
|---|---|---|
| `tests/test_canonical_schema.py` | 82 | Pydantic v2 CanonicalTransaction validation, IEEE-CIS/PaySim/India adapters |
| `tests/test_evaluator.py` | 26 | XGBoost metrics (accuracy, precision, recall, F1, ROC/PR-AUC, FPR, FNR, metadata) |
| `tests/test_threshold_calibration.py` | 21 | Candidate threshold sweep, objective selection, validation isolation guard, full-data readiness |
| `tests/test_feature_mapper.py` | 21 | CanonicalTransaction → IEEE-CIS feature dict mapping, duck typing, real adapter mapping |
| `tests/test_if_trainer.py` | 20 | Isolation Forest unsupervised training, label exclusion, score negation, reload matching |
| `tests/test_if_predictor.py` | 17 | AnomalyPredictor, anomaly_score convention, leakage removal, metadata checks |
| `tests/test_if_evaluator.py` | 16 | IF evaluation metrics against labels, FPR/FNR, mandatory caveat note |
| `tests/test_explainer.py` | 13 | TreeExplainer wrapper, global SHAP importance, per-prediction attribution, disclaimers |
| `tests/test_predictor.py` | 11 | FraudPredictor inference, probabilities, thresholds, single-dict scoring |
| `tests/test_ieee_cis_loader.py` | 11 | Transaction/identity merging, leakage prevention, sampling fraction checks |
| `tests/test_trainer.py` | 10 | XGBoost training, stratified splitting, early stopping, artifact reload |
| `tests/test_agent1_scorer.py` | 9 | Standalone ML scoring layer for Agent 1, score segregation, custom threshold overrides |
| `tests/test_preprocessor.py` | 8 | Sklearn ColumnTransformer pipeline, imputer, ordinal encoder, leakage columns |

Total: **265 tests, all passing.**

#### Test Execution Principles

- **Fast & Isolated**: All unit tests run against in-memory synthetic fixtures or cached lightweight test objects. None of the unit tests require loading the 1.3GB raw CSV files.
- **Model Independence**: Tests verify that XGBoost probabilities and Isolation Forest anomaly scores remain separate and unconfused.
- **Validation Isolation**: Threshold calibration tests assert that test-set evaluation cannot be performed during the threshold selection sweep.

### Agent Tests (Phase 4 Scheduled)

Test Agent 1 Anomaly Detector as a LangGraph node across five scenarios:
1. Normal transaction
2. Highly suspicious transaction
3. Malformed transaction input
4. Missing feature / sparse canonical input
5. Model artifact unavailable (graceful degradation)

### Pipeline Tests

Test the complete LangGraph sequence.

### ML Evaluation

Evaluate the anomaly-detection models using defined metrics on held-out test splits.

### Validation Tests

Verify that unsupported or inconsistent report content is rejected by the Output Validator.

### Integration Tests

Test interactions between:

- FastAPI
- LangGraph
- databases
- evidence sources
- report generation
- dashboard API

### End-to-End Tests

Run complete investigation cases through the system.

## Required Demonstration Cases

The project plan identifies:

- two clear fraud cases
- two clear legitimate cases
- one borderline case

## Success

Each test case should produce a case result with the expected investigation behavior and validation outcome.