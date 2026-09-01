# FILE: docs/07_RISK_AND_COMPLIANCE/RISK_SCORING.md

# Risk Scoring

## Purpose

Combine investigation signals into a final risk score.

## Signals

The project plan defines the following signals:

- anomaly score
- new device
- new beneficiary
- unusual timing
- network risk
- sanctions hit
- location anomaly

## Weighted Model

The project plan defines a weighted scoring model.

The implementation must keep:

- weights explicit
- signal definitions explicit
- score calculation deterministic
- score breakdown available to the analyst

## Output

The Risk Assessor provides:

- final risk score
- score breakdown
- regulatory matches
- recommended action
- confidence

## Important

Risk scoring must not be hidden inside an LLM.

The final score should be reproducible from its inputs and defined scoring configuration.