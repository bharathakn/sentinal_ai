# FILE: docs/02_AGENTS/OUTPUT_VALIDATOR.md

# Output Validator

## Purpose

Verify that the generated investigation report is consistent with the structured investigation data.

## Design Principle

The validator is deterministic and does not depend on an LLM to decide whether the report is valid.

## Validation Categories

The project plan identifies checks including:

- amounts match source data
- dates match source data
- entity references are supported
- regulatory references belong to the approved mapping
- recommended action matches the defined scoring logic
- source tags are present

## Result

Possible outcomes:

### VALIDATED

The report passes all required checks.

### NEEDS_HUMAN_REVIEW

One or more checks fail.

## Human Review

A failed validation must result in an analyst warning.

The report must not be presented as fully validated.

## Auditability

Validation results should remain associated with the case.

The system should preserve:

- individual validation checks
- validation status
- validation confidence
- generated report
- failure information where applicable