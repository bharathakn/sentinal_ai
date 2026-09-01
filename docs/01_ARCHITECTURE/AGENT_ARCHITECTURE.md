# FILE: docs/01_ARCHITECTURE/AGENT_ARCHITECTURE.md

# Agent Architecture

## Agent Sequence

Agent 1
→ Agent 2
→ Agent 3
→ Agent 4
→ Agent 5
→ Output Validator

## Agent Handoff Principle

Each agent receives the required state and produces structured output for the next stage.

## Agent 1

Input:

Raw transaction alert and required customer/transaction information.

Output:

- anomaly score
- isolation score
- confidence
- deviation features
- source/model metadata

## Agent 2

Input:

Case and transaction/customer identifiers.

Output:

Structured evidence from defined sources.

## Agent 3

Input:

Relevant account/network information.

Output:

- network risk
- detected pattern
- connected-account findings
- graph query metadata

## Agent 4

Input:

Outputs from Agents 1–3.

Output:

- final risk score
- score breakdown
- regulatory matches
- recommended action
- confidence

## Agent 5

Input:

Structured outputs from Agents 1–4.

Output:

Structured investigation report.

## Output Validator

Input:

Generated report + original structured evidence.

Output:

- validation status
- validation checks
- confidence
- final report if validated
- human-review warning if validation fails