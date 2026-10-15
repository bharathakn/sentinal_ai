# FILE: docs/04_MACHINE_LEARNING/DATASETS.md

# Datasets

## IEEE-CIS Fraud Detection Dataset

Status: **AVAILABLE AND VERIFIED** (`dataset/raw/ieee_cis/`)

Purpose:

Primary training and evaluation dataset for anomaly detection and SHAP explanations.

Verified Metrics: 590,540 train transactions, 144,233 train identity logs, 506,691 test transactions.

Verified Files: `train_transaction.csv`, `train_identity.csv`, `test_transaction.csv`, `test_identity.csv`, `sample_submission.csv`.

## PaySim

Status: **AVAILABLE AND VERIFIED** (`dataset/raw/paysim/PS_20174392719_1491204439457_log.csv`)

Purpose:

Supplementary fraud-pattern testing and network-related experimentation in Neo4j.

Verified Metrics: 6,362,620 synthetic mobile-money transactions (471 MB).

## Regulatory & Sanctions Source Datasets

Status: **AVAILABLE AND VERIFIED**

- Regulatory: `dataset/raw/regulatory/fatf/fatf-recommendations-2026.pdf` (1.5 MB) and `dataset/raw/regulatory/rbi/Master Directions on Fraud Risk Management in Commercial Banks .pdf` (1.8 MB)
- Sanctions: `dataset/raw/sanctions/ofac/ofac_sdn.csv` (5.5 MB) and `dataset/raw/sanctions/un/un_consolidated_sanctions.xml` (2.1 MB)

Purpose: Compliance rule mapping, watchlist filtering, and risk scoring grounding.

## Custom Synthetic India Dataset

Status: **COMPLETED AND VERIFIED** (`dataset/processed/custom_india/`)

Purpose:

Demonstrate India-relevant transaction patterns.

Characteristics:

- UPI, NEFT, RTGS payment channels
- Indian transaction timing patterns
- Project-defined regulatory thresholds (RTGS ≥ ₹2L, UPI ≤ ₹1L)
- Synthetic fraud patterns

Generated programmatically by `src/data/synthetic_india_generator.py`.

**This dataset is kept separate from IEEE-CIS performance calculations.**
Do not mix synthetic India data into IEEE-CIS evaluation metrics.

## Dataset Rules

- `dataset/raw/`: Original read-only source data.
- `dataset/processed/`: Derived/processed datasets.
- Do not represent synthetic data as real bank data.
- Document preprocessing.
- Document feature engineering.
- Document train/test methodology.
- Preserve reproducibility information.
- Record dataset versions where applicable.