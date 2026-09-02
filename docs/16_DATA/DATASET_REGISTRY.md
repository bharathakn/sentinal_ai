# Sentinel AI — Dataset Registry

## 1. Purpose

This document is the authoritative registry of all datasets used by Sentinel AI.

Every dataset used by the project must be recorded here.

The project must distinguish clearly between:

- Original raw datasets
- Processed datasets
- Generated synthetic datasets
- Training datasets
- Evaluation datasets
- Testing/demo datasets
- Graph/network datasets

Agents must not silently introduce a new dataset without documenting it here.

---

# 2. Dataset Overview

Sentinel AI dataset and reference material verification status:

1. IEEE-CIS Fraud Detection Dataset: **AVAILABLE AND VERIFIED**
2. PaySim Synthetic Financial Dataset: **AVAILABLE AND VERIFIED**
3. Regulatory Material (FATF & RBI): **AVAILABLE AND VERIFIED**
4. Sanctions Data (OFAC & UN): **AVAILABLE AND VERIFIED**
5. Custom Synthetic India Dataset: **PLANNED / TO BE GENERATED**

## Read-Only Data Architecture Rules

- `dataset/raw/`: Original read-only source data (immutable). Never edit or overwrite raw files directly.
- `dataset/processed/`: Intended location for derived, cleaned, or transformed dataset outputs.
- `synthetic data`: Programmatically generated data, clearly marked as synthetic, stored separately from raw data.

---

# 3. IEEE-CIS Fraud Detection Dataset

## Verification Status

**AVAILABLE AND VERIFIED**

## Purpose

Primary machine-learning dataset for anomaly detection, feature engineering, and model training (XGBoost, Isolation Forest, SHAP).

## Verified Local Location

`dataset/raw/ieee_cis/`

## Verified Files & Inspection Metrics

- `train_transaction.csv` (652 MB, **590,540 rows**, Contains `TransactionID`, `isFraud` target label, `TransactionDT`, `TransactionAmt`)
- `train_identity.csv` (26 MB, **144,233 rows**, Contains `TransactionID`, `id_01`..`id_38`, `DeviceType`, `DeviceInfo`)
- `test_transaction.csv` (585 MB, **506,691 rows**, Contains `TransactionID`)
- `test_identity.csv` (25 MB, **141,907 rows**, Contains `TransactionID`)
- `sample_submission.csv` (5.8 MB, **506,691 rows**, Contains `TransactionID`, `isFraud`)

## Verified Relationship & Schema

`TransactionID` is the joining key connecting transaction logs (`train_transaction.csv`) with device/identity features (`train_identity.csv`).

## Raw Data Rule

Raw IEEE-CIS files are read-only. Preprocessing must write derived datasets under `dataset/processed/`.

---

# 4. PaySim Synthetic Financial Dataset

## Verification Status

**AVAILABLE AND VERIFIED**

## Purpose

Secondary financial transaction network dataset for graph analysis in Neo4j and multi-account pattern detection.

## Verified Local Location

`dataset/raw/paysim/`

## Verified File & Inspection Metrics

- `PS_20174392719_1491204439457_log.csv` (471 MB, **6,362,620 rows**)
- **Schema**: `step`, `type`, `amount`, `nameOrig`, `oldbalanceOrg`, `newbalanceOrig`, `nameDest`, `oldbalanceDest`, `newbalanceDest`, `isFraud`, `isFlaggedFraud`.

## Important Rule

Do not load all 6.36M rows directly into Neo4j; extract representative fraud network subgraphs for prototype execution.

---

# 5. Regulatory Sources (FATF & RBI)

## Verification Status

**AVAILABLE AND VERIFIED**

## Verified Files & Locations

- **FATF**: `dataset/raw/regulatory/fatf/fatf-recommendations-2026.pdf` (1.5 MB)
- **RBI**: `dataset/raw/regulatory/rbi/Master Directions on Fraud Risk Management in Commercial Banks .pdf` (1.8 MB)

## Purpose

Grounding regulatory mappings and compliance references for Agent 4 (Risk Assessor) and Agent 5 (Explanation Generator).

---

# 6. Sanctions Data (OFAC & UN)

## Verification Status

**AVAILABLE AND VERIFIED**

## Verified Files & Locations

- **OFAC**: `dataset/raw/sanctions/ofac/ofac_sdn.csv` (5.5 MB)
- **UN**: `dataset/raw/sanctions/un/un_consolidated_sanctions.xml` (2.1 MB)

## Purpose

Watchlist screening and entity risk matching for Agent 2 (Evidence Gatherer) and Agent 4 (Risk Assessor).

---

# 7. Custom Synthetic India Dataset

## Verification Status

**PLANNED / TO BE GENERATED** (Does not exist yet)

## Purpose

Will be programmatically generated later during development to demonstrate UPI, NEFT, RTGS, and Indian banking scenarios (~10,000 synthetic transactions). It will be explicitly tagged as synthetic.
- Suspicious beneficiary behavior
- Layering
- Structuring
- Mule-account behavior
- Fraud-ring behavior

## Target Size

Approximately 10,000 transactions for the initial prototype.

## Generation

The dataset will be generated programmatically by the project implementation later and saved with synthetic markers.

The generation process must be deterministic when a fixed random seed is used.

## Important Rule

The synthetic dataset must be clearly labeled as synthetic.

It must never be presented as real Indian banking data.

---

# 8. Canonical Sentinel Transaction Model

The three datasets have different schemas.

Sentinel AI must therefore define an internal canonical transaction representation.

Conceptually:

Dataset-specific schema

→ preprocessing/normalization

→ Sentinel canonical transaction representation

→ agents

The agents should primarily work with the canonical representation rather than directly depending on raw dataset-specific column names.

---

# 7. Dataset Usage Rules

### IEEE-CIS

Primary ML training/evaluation dataset.

### PaySim

Secondary testing and network-analysis dataset.

### Custom India Dataset

Prototype-specific Indian scenario and demonstration dataset.

---

# 8. Dataset Provenance

For every dataset record:

- Dataset name
- Original source
- Download date
- Version or competition/dataset identifier where applicable
- Intended purpose
- License/usage terms
- Local storage location
- Preprocessing steps
- Whether the data is real, synthetic, or anonymized

---

# 9. Dataset Integrity

Agents must not:

- Modify raw files
- Rename raw files without documenting the change
- Delete raw files
- Commit huge raw datasets to Git
- Assume schemas without inspection
- Mix training and evaluation data incorrectly
- Introduce data leakage

Any derived dataset must have a documented relationship to its source dataset.

---

# 10. Model Evaluation Rule

Reported model metrics must come from actual experiments.

Numbers described in project planning documents are targets or previously proposed values until reproduced experimentally.

Agents must never fabricate model metrics.

Every final metric should record:

- Dataset
- Feature set
- Train/test methodology
- Model version
- Random seed
- Evaluation metrics
- Date/time of experiment