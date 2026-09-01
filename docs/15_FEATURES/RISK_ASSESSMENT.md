# FILE: docs/15_FEATURES/RISK_ASSESSMENT.md

# Feature — Risk Assessment

## Purpose

Combine investigation findings into a final risk assessment.

## Inputs

- anomaly results
- evidence results
- network results

## Outputs

- final score
- score breakdown
- regulatory matches
- recommended action
- confidence
- SAR recommendation where applicable

## Determinism

The scoring process must be reproducible from its documented signals and weights.

## Regulatory

Use the documented regulatory mapping.

Do not allow the LLM to invent regulatory references.