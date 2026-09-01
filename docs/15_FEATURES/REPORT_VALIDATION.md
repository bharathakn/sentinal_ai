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