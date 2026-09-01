# FILE: docs/00_PROJECT/REQUIREMENTS.md

# Sentinel AI — Requirements

## Functional Requirements

### Alert Ingestion

The system must accept a suspicious transaction alert.

The alert must contain the transaction information required to create an investigation case.

The system must create a unique case identifier.

### Investigation

The system must execute the investigation pipeline in the defined agent sequence.

### Anomaly Detection

The system must calculate an anomaly score.

The system must provide the major behavioral deviations contributing to the anomaly result.

### Evidence Gathering

The system must gather evidence from the defined prototype sources.

Evidence must retain source information and timestamps.

### Network Analysis

The system must analyze connected account relationships using Neo4j.

The system must identify defined suspicious network patterns.

### Risk Assessment

The system must combine investigation signals into a defined risk score.

The system must provide a score breakdown.

The system must map relevant findings to documented regulatory references.

### Report Generation

The system must generate a structured investigation report.

The report must follow the defined template.

The explanation generator must use only supplied structured evidence.

### Output Validation

The system must validate generated reports against source data.

If validation fails, the report must be flagged for human review.

### Dashboard

The dashboard must allow an analyst to view:

* case queue
* case details
* risk score
* evidence
* network graph
* audit report
* recommended action
* analyst action controls

### Audit Trail

Analyst decisions must be logged with the relevant timestamp and analyst information.

## Non-Functional Requirements

* Evidence traceability
* Structured agent handoffs
* Deterministic validation
* Clear separation between prototype mocks and production integrations
* Maintainable architecture
* Testability
* Explainability of ML results
* Security of credentials and sensitive data
