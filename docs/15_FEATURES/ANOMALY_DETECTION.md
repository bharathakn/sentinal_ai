# FILE: docs/15_FEATURES/ANOMALY_DETECTION.md

# Feature — Anomaly Detection

## Purpose

Determine whether the transaction is anomalous relative to customer behavior.

## Models

- XGBoost
- Isolation Forest

## Explainability

SHAP.

## Output

- anomaly score
- isolation score
- combined confidence
- top deviation features

## Required Signals

Refer to:

`docs/02_AGENTS/AGENT_1_ANOMALY_DETECTOR.md`

## Testing

Evaluate model behavior and output structure independently before integrating it into the complete pipeline.