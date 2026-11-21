# FILE: docs/08_REPORTING/VALIDATION_RULES.md

# Report Validation Rules

## Required Checks

### Amount Accuracy

Reported monetary values must correspond to source data.

### Date Accuracy

Reported dates and times must correspond to source data.

### Entity Validation

Entity references must be supported by available case data.

### Regulatory Validation

Regulatory references must belong to the approved regulatory mapping.

### Action Validation

Recommended action must be consistent with the defined risk logic.

### Source Tag Validation

Required findings must contain source information.

## Validation Result

All required checks pass:

`VALIDATED`

One or more required checks fail:

`NEEDS_HUMAN_REVIEW`

## Principle

Validation is deterministic and separate from LLM generation.

## Implementation (Phase 11)

| Rule | Check(s) in `src/agents/validator/` |
|---|---|
| Amount accuracy | CITATION_GROUNDING (numbers), BUNDLE_INTEGRITY (facts equal a rebuild from the case state) |
| Date accuracy | CITATION_GROUNDING (dates, times) |
| Entity validation | CITATION_GROUNDING (identifiers) |
| Regulatory validation | REGULATORY |
| Action validation | DECISION_CONSISTENCY |
| Source tag validation | STRUCTURE (every statement cites facts), BUNDLE_INTEGRITY (every fact sourced; audit trail complete) |
| Added in Phase 11 | LANGUAGE (no conclusive wording), LABEL_LEAKAGE (no ground truth) |

Details: `docs/02_AGENTS/OUTPUT_VALIDATOR.md`.