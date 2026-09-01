# FILE: docs/00_PROJECT/PROJECT_OVERVIEW.md

# Sentinel AI — Project Overview

## Project

Sentinel AI

## Team

Team 404 THINKER'S

## Problem

Financial institutions can detect suspicious transactions, but investigation after an alert remains heavily manual.

Analysts must gather evidence from multiple systems, investigate transaction behavior, identify connected accounts, assess risk, and produce documented reports.

## Solution

Sentinel AI automates the investigation workflow using five specialized agents connected through a LangGraph pipeline.

## Five-Agent Model

### Agent 1 — Anomaly Detector

Determines how abnormal a transaction is relative to customer behavior.

Primary model:

* XGBoost

Secondary model:

* Isolation Forest

Explainability:

* SHAP

### Agent 2 — Evidence Gatherer

Collects contextual evidence from multiple sources.

Planned sources include:

* Core Banking
* KYC
* Device Registry
* Beneficiary Database
* Sanctions/Watchlists
* Structured News
* Geolocation

### Agent 3 — Network Analyser

Analyzes connected accounts and transactions using Neo4j.

Detects patterns such as:

* layering
* structuring
* shell-company behavior
* fraud rings

### Agent 4 — Risk Assessor

Combines investigation signals into a risk score and maps findings to defined regulatory references.

### Agent 5 — Explanation Generator

Converts structured investigation data into an investigation report using strict evidence-grounding rules.

### Output Validator

Checks the generated report against source data and validation rules before the report reaches the analyst.

## User

Primary user:

Compliance analyst.

## Final User Experience

The analyst receives:

* case information
* risk score
* key findings
* evidence
* network analysis
* regulatory matches
* audit report
* validation status
* recommended action
* action controls

## Prototype Goal

Demonstrate a complete investigation pipeline using public/synthetic datasets and mocked banking APIs.
