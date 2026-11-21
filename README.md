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
* Groq API (Free tier)

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

* IEEE-CIS Fraud Detection Dataset (Available in `dataset/raw/ieee_cis/`)
* PaySim Synthetic Financial Dataset (Available in `dataset/raw/paysim/`)
* FATF & RBI Regulatory Material (Available in `dataset/raw/regulatory/`)
* OFAC & UN Sanctions Data (Available in `dataset/raw/sanctions/`)
* Custom Synthetic India Dataset (STATUS: COMPLETED & VERIFIED — `dataset/processed/custom_india/`)
* Mock KYC API
* Mock Core Banking API
* Mock Device Registry
* Mock Beneficiary Database
* Mock Geolocation Data
* Structured News API (NewsAPI)

## Current Status

Phases 1–12 are complete: canonical schema, ML models, Agents 1–5 (anomaly
detection, evidence gathering, network analysis, risk assessment, grounded
report generation), the deterministic Output Validator, and LangGraph
orchestration of the whole pipeline. Next is Phase 13, the ingestion API and
case store. The authoritative
status, plan and open decisions live in `docs/plans/CURRENT.md` and
`docs/plans/ROADMAP.md`.

Run one synthetic case end to end:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_investigation.py TXN_IND_202608_000977
```

## Quickstart & Verification

```bash
# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run complete test suite (265 tests)
pytest tests/ -v

# Run threshold calibration
python scripts/run_threshold_calibration.py

# Train ML models (15% development sample)
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_pipeline.py
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_isolation_forest.py

# Train ML models (Full IEEE-CIS dataset — requires >=16GB RAM)
SENTINEL_SAMPLE_FRAC=full python scripts/train_pipeline.py
SENTINEL_SAMPLE_FRAC=full python scripts/train_isolation_forest.py
```

## Documentation

Detailed project knowledge is maintained under `docs/`:
- `docs/plans/CURRENT.md`: Current project phase, verified metrics, hardware requirements, and active blockers.
- `docs/04_MACHINE_LEARNING/`: Model architectures, calibration reports, and evaluation results.
- `docs/16_DATA/CANONICAL_TRANSACTION_SCHEMA.md`: Canonical transaction specification and adapter mappings.

AI development instructions are maintained in:

* `CLAUDE.md`
* `AGENTS.md`

Agent-specific rules and skills are maintained under `.agents/`.
