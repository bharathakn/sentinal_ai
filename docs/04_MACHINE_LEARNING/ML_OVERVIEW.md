# FILE: docs/04_MACHINE_LEARNING/ML_OVERVIEW.md

# Machine Learning Overview

## Purpose

Machine learning is primarily used by the Anomaly Detector.

## Models

### XGBoost

Primary supervised fraud/anomaly model.

Status: **IMPLEMENTED AND VERIFIED** — see `XGBOOST_PIPELINE.md`.

### Isolation Forest

Secondary unsupervised anomaly detection model.

Status: **IMPLEMENTED AND VERIFIED** — see `ISOLATION_FOREST_PIPELINE.md`.

Outputs `anomaly_score` (higher = more anomalous). **Not a fraud probability.**
Must NOT be combined with XGBoost `fraud_probability` without a tested fusion strategy.

### SHAP

Explainability layer for feature contribution.

## Dataset

Primary dataset:

IEEE-CIS Fraud Detection Dataset.

Supplementary dataset:

PaySim.

Additional dataset:

Custom Synthetic India Dataset.

## Evaluation

The project plan identifies:

- accuracy
- precision
- recall
- F1 score
- AUC-ROC
- false-positive rate
- false-negative rate

## Important Principle

Reported performance metrics must be generated from actual evaluation runs.

The project documentation must distinguish planned target values from measured experimental results.