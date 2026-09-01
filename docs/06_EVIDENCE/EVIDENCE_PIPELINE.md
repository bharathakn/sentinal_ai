# FILE: docs/06_EVIDENCE/EVIDENCE_PIPELINE.md

# Evidence Pipeline

## Purpose

Collect and normalize investigation evidence from multiple sources.

## Sources

- Core Banking
- KYC
- Device Registry
- Beneficiary Database
- Sanctions
- News
- Geolocation

## Evidence Lifecycle

Source
→ Query
→ Result
→ Normalize
→ Attach source metadata
→ Attach timestamp
→ Store in case state
→ Pass to downstream agent

## Evidence Requirements

Every important evidence item should identify:

- source
- timestamp
- value/result
- associated case
- relevant entity or transaction

## Evidence Principle

Evidence must remain distinguishable from:

- model predictions
- calculated scores
- LLM-generated explanations

## Prototype

Banking sources are mocked for the prototype where specified in the project plan.