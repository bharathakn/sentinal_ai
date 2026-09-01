# FILE: docs/15_FEATURES/REPORT_GENERATION.md

# Feature — Report Generation

## Purpose

Generate an audit-ready investigation report from structured investigation data.

## Sections

1. Case Summary
2. Anomaly Findings
3. Evidence Summary
4. Network Analysis
5. Regulatory Assessment
6. Recommended Action
7. Source Audit Trail

## Grounding

The generator must use only supplied structured data.

## Missing Data

Missing or empty fields should be represented as:

`Not identified`

## Validation

Generated reports must pass through the Output Validator.