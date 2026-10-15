# FILE: docs/14_OPERATIONS/DEVELOPMENT_SETUP.md

# Development Setup

## Required Environment

The project requires:

- Python 3.11+
- Virtual environment (`.venv`)
- Git with branch workflow
- Optional: Neo4j (Agent 3 graph network analysis)
- Optional: MongoDB Atlas (case storage)
- Optional: Groq API key (free tier, for report generation agents)

## Local Python Environment Setup

```bash
# 1. Clone repository and navigate to root
cd Sentinal_AI

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install core dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Dependencies Installed (`requirements.txt`)

- **Core ML**: `xgboost>=2.0.0`, `scikit-learn>=1.4.0`, `shap>=0.45.0`
- **Data & Schemas**: `pandas>=2.1.0`, `numpy>=1.26.0`, `pydantic>=2.0.0`
- **Persistence**: `joblib>=1.3.0`
- **Testing**: `pytest>=8.0.0`, `pytest-cov>=5.0.0`

## Dataset Directory Layout

Raw datasets are read-only and placed under `dataset/raw/`:

```
dataset/
├── raw/
│   ├── ieee_cis/               # train_transaction.csv, train_identity.csv, test_*.csv
│   ├── paysim/                 # PS_20174392719_1491204439457_log.csv
│   ├── regulatory/fatf/        # fatf-recommendations-2026.pdf
│   ├── regulatory/rbi/         # RBI Master Directions on Fraud Risk Management.pdf
│   ├── sanctions/ofac/         # ofac_sdn.csv
│   └── sanctions/un/           # un_consolidated_sanctions.xml
└── processed/
    └── custom_india/           # custom_india_transactions.csv (synthetic data)
```

## Running Verification Tests

Run all 265 unit and integration tests:

```bash
.venv/bin/python -m pytest tests/ -v
```

All tests execute in ~12 seconds using in-memory synthetic fixtures; raw dataset files are not loaded during test suite execution.

## Machine Learning Execution Workflows

### 1. Model Inference (No Training)

Trained artifacts are cached in `models/xgboost/v1/` and `models/isolation_forest/v1/`. For inference, load existing artifacts directly:

```python
from src.ml.agent1_scorer import Agent1Scorer
from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter

scorer = Agent1Scorer()
tx = IEEECISAdapter.from_row(raw_row)
score_result = scorer.score(tx)
# score_result["xgboost"]["fraud_probability"]
# score_result["iforest"]["anomaly_score"]
```

### 2. Threshold Calibration

Re-run threshold sweeps on the held-out validation split:

```bash
python scripts/run_threshold_calibration.py
```

### 3. Training Models

#### Development Mode (15% Stratified Sample)
Recommended for development on standard developer laptops (requires 4–8GB RAM):

```bash
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_pipeline.py
SENTINEL_SAMPLE_FRAC=0.15 python scripts/train_isolation_forest.py
```

#### Full IEEE-CIS Mode (590,540 rows)
Full dataset training is fully supported by the software without row limits or column truncation:

```bash
SENTINEL_SAMPLE_FRAC=full python scripts/train_pipeline.py
SENTINEL_SAMPLE_FRAC=full python scripts/train_isolation_forest.py
```

> [!NOTE]
> **Hardware Policy**: Full-dataset training merges 590,540 transactions and 144,233 identity rows into a 434-column DataFrame. Fitting 500 gradient-boosted trees and 200 isolation trees requires $\ge 16\text{GB}$ available host RAM. Machines with less available RAM should use the validated 15% sample baseline to prevent Linux OOM-killer termination.

## Service Roles & Architecture Distinction

- **Groq API**: External LLM Provider (used for structured explanation and investigation report generation)
- **Mock Banking APIs**: Core Banking, KYC, Device Registry, Beneficiary Database, Geolocation (simulated internal services)
- **MongoDB Atlas**: Case object & investigation output persistent storage
- **Neo4j**: Financial account/transaction graph & network analysis
- **NewsAPI**: External structured public-news evidence
- **Regulatory / Sanctions Sources**: Approved offline source data (FATF, RBI, OFAC, UN)