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
5. Custom Synthetic India Dataset: **AVAILABLE AND VERIFIED (SYNTHETIC DATA)**

## Read-Only Data Architecture Rules

- `dataset/raw/`: Original read-only source data (immutable). Never edit or overwrite raw files directly.
- `dataset/processed/`: Intended location for derived, cleaned, or transformed dataset outputs.
- `synthetic data`: Programmatically generated data, clearly marked as synthetic, stored separately from raw data.
- `dataset reproducibility`: All synthetic datasets must be generated programmatically using fixed random seeds. Manual editing of synthetic CSV files is strictly prohibited.

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

**AVAILABLE AND VERIFIED (SYNTHETIC DATA)**

> [!IMPORTANT]
> **SYNTHETIC DATA DISCLAIMER**: This dataset is 100% programmatically generated synthetic data. It contains zero real customer PII, zero real banking credentials, and zero real transaction records. It must never be described or presented as real Indian banking data.

## Verified Location & Files

* **Target Directory:** `dataset/processed/custom_india/`
* **Generated CSV Artifacts & Storage Metrics:**
  * `customers.csv` (1,200 synthetic customer entity records, 126.7 KB)
  * `accounts.csv` (1,500 synthetic bank account records with `SYN99` prefix, 167.6 KB)
  * `devices.csv` (1,400 synthetic device fingerprint records, 157.7 KB)
  * `beneficiaries.csv` (2,000 synthetic beneficiary mapping records, 192.5 KB)
  * `transactions_features.csv` (10,000 transaction observation feature vectors $X$, 3.14 MB)
  * `transactions_targets.csv` (10,000 ground-truth target metadata vectors $y$, 709.0 KB)
  * `graph_edges.csv` (10,000 directed transfer edges for Neo4j import, 1.14 MB)
  * `dataset_metadata.json` (Provenance, seed configuration, and distribution manifest, 1.18 KB)

## Dataset Specifications & Statistics

* **Total Transactions:** **10,000**
* **Supporting Entities:** **1,200** Customers, **1,500** Accounts, **1,400** Devices, **2,000** Beneficiaries.
* **Random Seed:** **`42`** (Configurable reproducible seed).
* **Generation Engine:** Programmatic Python generator script (`src/data/synthetic_india_generator.py`).
* **Temporal Window:** 30 contiguous days (`2026-08-01T00:15:43+05:30` to `2026-08-30T23:59:25+05:30` IST).

## Indian Payment Channels Represented

* **UPI (Unified Payments Interface):** **7,070** transactions (70.70%) — Enforces NPCI per-transaction limit ($\le \text{₹1,00,000}$).
* **NEFT (National Electronic Funds Transfer):** **2,213** transactions (22.13%) — Standard batch retail & vendor transfers.
* **RTGS (Real Time Gross Settlement):** **717** transactions (7.17%) — Enforces mandatory RBI regulatory minimum ($\ge \text{₹2,00,000}$).

## Represented Scenarios (12 Distinct Behaviors)

1. `SCENARIO_1_NORMAL_LEGITIMATE`: **8,200** transactions (82.00%) — Benign consumer transfers with realistic noise.
2. `SCENARIO_2_HIGH_VALUE_SPIKE`: **200** transactions — Sudden high-amount transfers ($8\times$–$15\times$ baseline average).
3. `SCENARIO_3_RAPID_BURST`: **150** transactions — Rapid sequential UPI transfers on newly added beneficiaries.
4. `SCENARIO_4_NEW_BENEFICIARY_LARGE_TX`: **150** transactions — Large NEFT/RTGS transfers to beneficiaries created $< 30$ minutes prior.
5. `SCENARIO_5_NEW_DEVICE_SUSPICIOUS`: **150** transactions — Unrecognised device logins with high geographic location deltas.
6. `SCENARIO_6_STRUCTURING_SPLITTING`: **150** transactions — Transfers structured just below round threshold limits (e.g., ₹49,500 / ₹98,500).
7. `SCENARIO_7_LAYERING_NETWORK`: **200** transactions — Rapid multi-hop RTGS/NEFT passthrough transfers ($A \to B \to C \to D$).
8. `SCENARIO_8_MULE_PASS_THROUGH`: **200** transactions — Immediate depletion of low-balance proxy accounts.
9. `SCENARIO_9_FRAUD_RING_HUB`: **200** transactions — Multi-account fan-in transfers targeting centralized hub nodes.
10. `SCENARIO_10_IMPOSSIBLE_TRAVEL`: **150** transactions — Geodesic location discrepancy $> 1,200$ km within short time windows.
11. `SCENARIO_11_SHARED_DEVICE_IP`: **150** transactions — Multiple customer accounts sharing subnets/hardware fingerprints.
12. `SCENARIO_12_MIXED_BORDERLINE_TRAVEL`: **100** transactions — Legitimate high-distance travel / vacation transfers (`is_fraud = 0`).

## Intended Multi-Purpose Use

The dataset is explicitly designed for **multiple system purposes**:
- **Model Development & Training:** Feature engineering and baseline model fitting (XGBoost, Isolation Forest).
- **Model Testing & Benchmark Evaluation:** Temporal Out-of-Time (OOT) evaluation (Days 1–21 Train, Days 22–30 Test).
- **Behavioral Anomaly Detection:** Evaluating unsupervised anomaly scoring engines.
- **Neo4j Graph Network Analysis:** Bulk loading directed `:TRANSFERRED_TO` relationships for Agent 3 Cypher queries.
- **Agent Pipeline Handoffs:** Testing structured case data transfer across Agents 1 through 5.
- **System Demonstrations:** End-to-end user interface and compliance dashboard workflow validation.

## Validation Status

**VERIFIED AND PASSED**
- All 6 core structural, referential, regulatory, and zero-leakage validation checks passed.
- All 12 scenarios verified and statistically represented.
- ML suitability verified as **READY**. Zero model performance metrics are claimed at this stage (pending formal training phase).

## Known Limitations

- **Synthetic Domain:** All entities, VPAs, and bank accounts are simulated mock data.
- **Bounded Scale:** Fixed to 10,000 transaction events over a 30-day window.
- **Simplified Regulatory Model:** Approximates NPCI UPI caps and RBI RTGS limits without modeling intraday liquidity constraints or interbank clearing queues.

## Data Governance & Reproducibility Rules

1. **Read-Only Source Data:** All original raw datasets (`dataset/raw/`) remain read-only and immutable.
2. **Programmatic Generation:** The synthetic dataset is generated programmatically via `src/data/synthetic_india_generator.py` using fixed random seed `42`.
3. **Prohibition of Manual Editing:** Manual editing or modification of generated CSV files is strictly prohibited.
4. **Reproducible Future Changes:** Any future schema modifications, scenario updates, or row-count expansions must be executed through the Python generator script to guarantee full reproducibility.

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