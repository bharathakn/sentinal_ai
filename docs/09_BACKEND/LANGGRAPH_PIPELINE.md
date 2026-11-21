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

## Case entry point and label firewall (Phase 9.5)

`src/agents/sentinel_pipeline.new_case_state(transaction)` is the only
supported entry point. It assigns `case_id` / `case_created_at_utc` and strips
dataset ground truth (`is_fraud`, `metadata.risk_label`,
`metadata.scenario_id`) so no agent — and no LLM prompt built from agent
outputs — can see labels. `metadata.alert_id` and `is_flagged_fraud` are kept
(they describe the monitoring alert).

Until LangGraph orchestration (Phase 12), `src/agents/investigation.Investigator`
runs Agents 1–4 sequentially with the same state contract.
