# FILE: docs/15_FEATURES/ANOMALY_DETECTION.md

# Feature — Anomaly Detection

## Purpose

Detect statistically unusual and fraudulent financial transactions relative to normal customer and network behavior.

## Implementation Status

- **ML Inference Layer (Phases 2 & 3 — COMPLETE & VERIFIED)**:
  - Supervised fraud classifier: XGBoost (`src/ml/trainer.py`, `src/ml/predictor.py`)
  - Unsupervised anomaly cross-check: Isolation Forest (`src/ml/if_trainer.py`, `src/ml/if_predictor.py`)
  - Unified inference engine: `src/ml/agent1_scorer.py` (`Agent1Scorer`)
  - Feature mapping from canonical schema: `src/ml/feature_mapper.py`
  - Explainability: SHAP (`src/ml/explainer.py`)
  - Threshold calibration: `src/ml/threshold_calibration.py` (XGBoost=0.80, IF=0.468)
- **Agent Node Integration (Phase 4 — NEXT PLANNED PHASE)**:
  - LangGraph node wiring, state graph compilation, and `combined_confidence` score fusion.

## Models & Scoring Distinction

| Model | Type | Metric / Output | Calibrated Threshold |
|---|---|---|---|
| XGBoost | Supervised | `fraud_probability` ∈ [0, 1] | 0.80 (Precision=0.714, Recall=0.540, F1=0.615) |
| Isolation Forest | Unsupervised | `anomaly_score` ∈ ℝ (higher = more anomalous) | 0.468 (FPR=0.035, F1=0.293) |

> **Principle**: Anomaly score is not a probability of fraud. The two signals are generated independently and kept segregated in the output.

## Documentation References

- Architecture & Overview: `docs/04_MACHINE_LEARNING/ML_OVERVIEW.md`
- XGBoost Pipeline: `docs/04_MACHINE_LEARNING/XGBOOST_PIPELINE.md`
- Isolation Forest Pipeline: `docs/04_MACHINE_LEARNING/ISOLATION_FOREST_PIPELINE.md`
- Evaluation Results: `docs/04_MACHINE_LEARNING/EVALUATION_RESULTS.md`
- Threshold Calibration: `docs/04_MACHINE_LEARNING/THRESHOLD_CALIBRATION.md`
- Agent 1 Specification: `docs/02_AGENTS/AGENT_1_ANOMALY_DETECTOR.md`

## Testing

Verified with **265 automated tests**:

```bash
.venv/bin/python -m pytest tests/ -v
```