# FILE: docs/02_AGENTS/AGENT_1_ANOMALY_DETECTOR.md

# Agent 1 — Anomaly Detector

## Purpose

Determine how abnormal a transaction is relative to the customer's normal behavior.

## Primary Model

XGBoost.

## Secondary Model

Isolation Forest.

The secondary model provides an unsupervised cross-check.

## Behavioral Signals

The project plan identifies signals including:

- transaction amount versus historical average
- transaction timing
- device identity
- device type
- operating system
- geographic distance
- recent transaction frequency
- beneficiary history
- card-present status
- browser/application information

## Outputs

The agent produces:

- anomaly score
- isolation score
- combined confidence
- top deviation features
- model/source metadata

## Explainability

SHAP is used to identify feature contributions.

## Handoff

The output is passed to the Evidence Gatherer and subsequently contributes to risk assessment.

## Requirements

- Use structured output.
- Preserve model metadata.
- Preserve relevant timestamps.
- Do not generate unsupported investigative claims.