# FILE: docs/01_ARCHITECTURE/DATA_FLOW.md

# Data Flow

## Investigation Lifecycle

### 1. Alert

Transaction monitoring system generates an alert.

### 2. Ingestion

FastAPI receives and validates the alert.

A case identifier is created.

### 3. Anomaly Analysis

Transaction behavior is analyzed.

### 4. Evidence Collection

External and internal prototype data sources are queried.

### 5. Network Investigation

Connected accounts and transaction relationships are analyzed.

### 6. Risk Assessment

Signals are combined into the defined risk score.

### 7. Explanation

Structured evidence is converted into the investigation report.

### 8. Validation

The report is compared against source data.

### 9. Persistence

The case and investigation results are stored.

### 10. Presentation

The analyst views the case through the dashboard.

### 11. Analyst Decision

The analyst confirms the appropriate action.

The decision is recorded in the audit trail.