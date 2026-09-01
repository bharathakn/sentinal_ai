# FILE: docs/09_BACKEND/LANGGRAPH_PIPELINE.md

# LangGraph Investigation Pipeline

## Purpose

Coordinate the investigation workflow.

## Nodes

1. Anomaly Detector
2. Evidence Gatherer
3. Network Analyser
4. Risk Assessor
5. Explanation Generator
6. Output Validator

## Sequence

Anomaly Detector
→ Evidence Gatherer
→ Network Analyser
→ Risk Assessor
→ Explanation Generator
→ Output Validator

## State

The case state must carry the information required by downstream stages.

## Requirements

- structured handoffs
- error handling
- state preservation
- deterministic progression
- clear failure behavior

## Final State

A completed case should contain the investigation results, validation outcome, and information required by the dashboard and audit trail.