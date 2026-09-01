# FILE: README.md

# Sentinel AI

## Team

Team 404 THINKER'S

## Problem Statement

Sentinel AI addresses the investigation gap that exists after financial institutions detect suspicious transactions.

Existing systems can generate fraud alerts, but compliance analysts still need to manually collect evidence, investigate transaction context, analyze connected accounts, assess risk, and prepare documented reports.

Sentinel AI is designed to automate this investigation workflow while keeping the final investigation evidence-grounded and auditable.

## Core Objective

Build a system that receives a suspicious transaction alert and automatically:

1. Analyze transaction anomalies.
2. Gather contextual evidence.
3. Analyze connected financial networks.
4. Assess risk using defined scoring and regulatory mappings.
5. Generate a structured investigation report.
6. Validate the report against source evidence.
7. Present the result to a compliance analyst.

## Core Pipeline

Alert
→ FastAPI ingestion
→ LangGraph controller
→ Anomaly Detector
→ Evidence Gatherer
→ Network Analyser
→ Risk Assessor
→ Explanation Generator
→ Output Validator
→ Compliance Dashboard
→ Analyst Review

## Primary Technologies

* Python 3.11
* FastAPI
* LangGraph
* Pydantic
* XGBoost
* Scikit-learn
* Pandas
* NumPy
* SHAP
* Neo4j
* MongoDB Atlas
* Redis (optional)
* React
* Tailwind CSS
* Recharts
* React Force Graph
* Claude API

## Main Agents

1. Anomaly Detector
2. Evidence Gatherer
3. Network Analyser
4. Risk Assessor
5. Explanation Generator

## Reliability Principle

The LLM must generate explanations from structured evidence rather than inventing investigative facts.

Every important factual output must be traceable to source data and timestamps.

A deterministic validation layer must check the generated report before it reaches the analyst.

## Prototype Data Sources

* IEEE-CIS Fraud Detection Dataset
* PaySim
* Custom Synthetic India Dataset
* Mock KYC API
* Mock Core Banking API
* Device Registry
* Beneficiary Database
* Sanctions sources
* Structured News API
* Geolocation data

## Current Status

Project initialization.

## Documentation

Detailed project knowledge is maintained under `docs/`.

AI development instructions are maintained in:

* `CLAUDE.md`
* `AGENTS.md`

Agent-specific rules and skills are maintained under `.agents/`.
