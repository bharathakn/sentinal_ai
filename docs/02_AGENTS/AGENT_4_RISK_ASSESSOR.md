# FILE: docs/02_AGENTS/AGENT_4_RISK_ASSESSOR.md

# Agent 4 — Risk Assessor

## Purpose

Combine outputs from the preceding investigation stages into a risk assessment.

## Inputs

- Agent 1 anomaly results
- Agent 2 evidence
- Agent 3 network analysis

## Risk Signals

The project plan identifies:

- anomaly score
- new device
- new beneficiary
- unusual timing
- network risk
- sanctions result
- location anomaly

## Weighting

The project plan defines a weighted scoring approach.

The weights must be maintained as explicit project configuration rather than hidden inside an LLM prompt.

## Output

The agent produces:

- final risk score
- score breakdown
- regulatory matches
- recommended action
- confidence information
- SAR recommendation where applicable

## Regulatory Mapping

The project plan identifies FATF typologies and RBI AML references.

The exact mapping must remain documented and auditable.

## Important Rule

The LLM must not independently invent regulatory mappings.

Regulatory references must come from the project's approved mapping.