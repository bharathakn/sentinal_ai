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