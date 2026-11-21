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

## Version

**v2.0.0** (2026-11-21, generator `src/data/synthetic_india_generator.py`, seed 42).
v1 is archived (not deleted) at `dataset/processed/_archive/custom_india_v1/`.

**Why v2:** v1 drew sender, receiver, device, location and every behavioural
flag independently at random. Network scenarios (layering, mule, ring,
structuring) existed only as labels — their transactions had no chain, hub or
burst structure, so graph analysis could not find them — and the entity
tables contradicted the transaction flags (registered beneficiary pairs matched
0.08% of transactions; 699 "near home" transactions had coordinates > 500 km
away; `tx_frequency_24h` was random). `graph_edges.csv` also carried
`scenario_id` (a label).

v2 generates each scenario as an actual transaction pattern and derives every
behavioural feature from the generated ledger and entity tables.

## Location & Files

* **Directory:** `dataset/processed/custom_india/` (git-ignored; regenerate with
  `python scripts/generate_synthetic_dataset.py`)
  * `customers.csv` — 1,200 customers (22 Indian cities)
  * `accounts.csv` — 1,500 accounts (33 `MULE_SUSPECT`, opened 5–60 days before the window)
  * `devices.csv` — 2,298 devices (registered devices + devices first seen in-window)
  * `beneficiaries.csv` — 8,081 sender→receiver records (established payees + payees added in-window)
  * `transactions_features.csv` — 10,000 transactions (features only)
  * `transactions_targets.csv` — 10,000 labels: `is_fraud`, `risk_label`, `scenario_id`, `pattern_id`, `alert_id`
  * `graph_edges.csv` — 10,000 edges (no label columns)
  * `dataset_metadata.json`

## Specifications

* **Window:** 2026-08-01 to 2026-08-30 IST. Transaction ids are chronological.
* **Labels:** LEGITIMATE 8,200 · FRAUDULENT 1,338 · BORDERLINE 462.
* **Channels:** UPI 6,841 · NEFT 3,013 · RTGS 146 (UPI ≤ ₹1,00,000; RTGS ≥ ₹2,00,000).
* **Criminal pool:** mules, layering intermediaries, ring members, structuring
  senders and recipients, and burst / account-takeover payees come from a
  small pool (MULE_SUSPECT accounts + ~6% of others). Victims are random customers.

## Consistency guarantees (validator check 7)

* Every transaction pair has a beneficiary record added before it;
  `is_new_beneficiary` = added < 30 days earlier; `time_since_beneficiary_added_min` derived from it.
* `is_new_device` = device first seen < 7 days earlier, or device owned by another customer.
* `distance_from_home_km` = haversine(home, transaction coordinates); `tx_city` names the real location.
* `tx_frequency_24h`, `time_since_last_tx_sec`, balances computed from the chronological ledger.

## Scenarios (12)

| Scenario | Txns | Generated pattern |
|---|---|---|
| 1 Normal legitimate | 8,200 | Established payee (80%) or payee added 1–29 days earlier; home location (97%); amount ≈ account baseline |
| 2 High-value spike | 200 | 8–15× baseline to an established payee (50% fraud / 50% borderline) |
| 3 Rapid burst | 150 | 5–10 UPI payments within ~1 h to new payees, usually from an unregistered new device |
| 4 New beneficiary, large | 150 | ₹1.5–4.5 L NEFT to a payee added 2–28 min earlier |
| 5 New device | 150 | Unregistered new device, 100–500 km from home, payee added 10–60 min earlier |
| 6 Structuring | 150 | 4–6 transfers of ₹45,000–49,999 or ₹95,000–99,999 within ~20 h to 2–4 payees |
| 7 Layering | 200 | Chain of 3–5 hops, 10–120 min apart, each hop 97–99.5% of the previous |
| 8 Mule pass-through | 200 | 3–5 sources pay a mule, which forwards 85–95% within hours |
| 9 Fraud ring | 200 | Cycle through 4–6 accounts plus member → hub transfers within ~2 days |
| 10 Impossible travel | 150 | Payment 1,200–2,500 km from home within 30–180 min of a home payment |
| 11 Shared device | 150 | 3–5 other customers' accounts transact from one device / IP |
| 12 Borderline travel | 100 | Legitimate long-distance travel payment (BORDERLINE) |

## Intended Multi-Purpose Use

The dataset is explicitly designed for **multiple system purposes**:
- **Model Development & Training:** Feature engineering and baseline model fitting (XGBoost, Isolation Forest).
- **Model Testing & Benchmark Evaluation:** stratified 70/15/15 split (see the India behavioural model doc).
- **Behavioral Anomaly Detection:** Evaluating unsupervised anomaly scoring engines.
- **Neo4j Graph Network Analysis:** Bulk loading directed `:TRANSFERRED_TO` relationships for Agent 3 Cypher queries.
- **Agent Pipeline Handoffs:** Testing structured case data transfer across Agents 1 through 5.
- **System Demonstrations:** End-to-end user interface and compliance dashboard workflow validation.

## Validation Status

**VERIFIED AND PASSED**
- All 7 validation checks pass, including check 7 (behavioural consistency).
- India behavioural model (Agent 1) trained on v2: see `docs/04_MACHINE_LEARNING/INDIA_BEHAVIOUR_MODEL.md`.

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

The three datasets have entirely different schemas.

Sentinel AI defines an internal canonical transaction representation (`CanonicalTransaction`) that every dataset is normalized into before entering the agent pipeline.

```
Dataset-specific schema
  → Dataset Adapter (IEEE-CIS / PaySim / India Synthetic)
  → CanonicalTransaction (Pydantic v2 validated)
  → Agents (Agent 1 → Agent 2 → … → Output Validator)
```

Agents work with `CanonicalTransaction` and must never directly depend on raw dataset-specific column names.

**Full specification:** `docs/16_DATA/CANONICAL_TRANSACTION_SCHEMA.md`

**Implementation:**
- Model: `src/schemas/canonical_transaction.py`
- Adapters: `src/schemas/adapters/`
- Tests: `tests/test_canonical_schema.py` (82 tests, all passing)

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