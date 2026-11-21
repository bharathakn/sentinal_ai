# FILE: docs/15_FEATURES/REPORT_VALIDATION.md

# Feature — Report Validation

## Purpose

Prevent unsupported or inconsistent information from being presented as a validated investigation report.

## Checks

- amounts
- dates
- entities
- regulatory references
- recommended action
- source tags

## Results

`VALIDATED`

or

`NEEDS_HUMAN_REVIEW`

## Failure Behavior

A failed report must be flagged.

The analyst must be informed that manual verification is required.

## Implementation

Implemented in Phase 11 (`src/agents/validator/`). Seven deterministic checks
cover the items above, plus wording and label leakage. If an LLM-written
report fails, a template report built from the same evidence is validated and
presented instead. The failed LLM report is kept for audit. See
`docs/02_AGENTS/OUTPUT_VALIDATOR.md`.