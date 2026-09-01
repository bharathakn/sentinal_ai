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

Sentinel AI currently uses three main dataset categories:

1. IEEE-CIS Fraud Detection Dataset
2. PaySim Synthetic Financial Dataset
3. Custom Synthetic India Dataset

The first two datasets are already available locally.

The Custom Synthetic India Dataset will be generated as part of the project.

---

# 3. IEEE-CIS Fraud Detection Dataset

## Purpose

Primary machine-learning dataset for the anomaly detection system.

The dataset is used primarily for:

- Feature engineering
- XGBoost training
- Isolation Forest experimentation
- Model evaluation
- Fraud classification experiments
- SHAP-based model explanation
- Agent 1 development and testing

## Local Location

The raw dataset must be stored under:

`dataset/raw/ieee-cis/`

## Expected Files

The directory should contain:

- `train_transaction.csv`
- `train_identity.csv`
- `test_transaction.csv`
- `test_identity.csv`
- `sample_submission.csv`

## Important Relationship

`train_transaction.csv` and `train_identity.csv` are related through the transaction identifier.

The same principle applies to the test transaction and identity datasets.

Agents must inspect the actual schema before implementing preprocessing.

Do not assume that every field is present or populated.

## Raw Data Rule

The original IEEE-CIS files must never be modified.

All preprocessing must create a separate processed representation.

---

# 4. PaySim Synthetic Financial Dataset

## Purpose

PaySim is the secondary financial dataset.

It is intended to provide:

- Additional fraud-pattern coverage
- Transaction-network data
- Graph analysis input
- Agent 3 testing
- Synthetic financial behavior examples
- Additional end-to-end testing scenarios

## Local Location

The raw dataset must be stored under:

`dataset/raw/paysim/`

## Expected File

The current downloaded dataset contains:

`PS_20174392719_1491204439457_log.csv`

## Important Rule

Do not automatically load the entire PaySim dataset into Neo4j.

The dataset is large and the Neo4j environment is intended for prototype-scale graph analysis.

Agents must first determine an appropriate subset, transformation, or representative network extraction strategy.

---

# 5. Custom Synthetic India Dataset

## Status

Not yet generated.

## Purpose

The Custom Synthetic India Dataset is intended to make the Sentinel AI demonstration relevant to Indian financial transaction scenarios.

It should represent scenarios such as:

- UPI transactions
- NEFT transactions
- RTGS transactions
- Indian account behavior
- Indian transaction timing
- Indian-style customer profiles
- Indian fraud patterns
- Suspicious beneficiary behavior
- Layering
- Structuring
- Mule-account behavior
- Fraud-ring behavior

## Target Size

Approximately 10,000 transactions for the initial prototype.

## Generation

The dataset should be generated programmatically by the project implementation.

The generation process must be deterministic when a fixed random seed is used.

## Important Rule

The synthetic dataset must be clearly labeled as synthetic.

It must never be presented as real Indian banking data.

---

# 6. Canonical Sentinel Transaction Model

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