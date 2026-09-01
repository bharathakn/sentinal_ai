# FILE: docs/08_REPORTING/EVIDENCE_GROUNDING.md

# Evidence Grounding

## Purpose

Ensure generated investigation reports remain grounded in structured investigation evidence.

## Core Principle

The LLM writes from supplied data.

It does not independently determine facts.

## Required Behavior

The generator must:

- use only supplied data
- avoid speculation
- avoid unsupported inference
- preserve source tags
- preserve timestamps
- follow the approved report structure
- identify unavailable fields as `Not identified`

## Source Traceability

Important factual statements must be traceable to source fields.

## Validation

Every generated report passes through the Output Validator.

## Failure

If the validator identifies unsupported or inconsistent information:

The report becomes `NEEDS_HUMAN_REVIEW`.