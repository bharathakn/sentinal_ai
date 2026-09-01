# FILE: docs/02_AGENTS/AGENT_5_EXPLANATION_GENERATOR.md

# Agent 5 — Explanation Generator

## Purpose

Convert structured investigation data into a formal investigation report.

## LLM Role

The LLM is a report writer.

It receives structured evidence from previous pipeline stages.

It must not act as an independent source of investigative facts.

## Evidence Grounding

The generator must:

- use only supplied data
- preserve source information
- preserve timestamps
- avoid unsupported claims
- avoid speculation
- use the defined report structure
- represent missing fields as `Not identified`

## Report Sections

1. Case Summary
2. Anomaly Findings
3. Evidence Summary
4. Network Analysis
5. Regulatory Assessment
6. Recommended Action
7. Source Audit Trail

## Validation Dependency

The generated report must pass the Output Validator before being treated as validated.

## Failure Handling

If validation fails:

- do not mark the report as validated
- retain validation results
- flag the case for human review