# Sentinel AI — Data Handling Rules

## 1. Purpose

This document defines how Sentinel AI handles datasets and generated data.

These rules apply to every AI coding agent.

---

# 2. Raw Data Is Read-Only

Raw datasets are immutable.

Expected structure:

dataset/raw/

Raw data must never be edited directly.

Agents must create processed or derived datasets separately.

---

# 3. Recommended Data Flow

Raw Dataset

↓

Data Inspection

↓

Validation

↓

Cleaning / Preprocessing

↓

Feature Engineering

↓

Processed Dataset

↓

Model Training / Graph Construction / Testing

Raw data must remain unchanged throughout this process.

---

# 4. No Silent Data Transformation

Any significant transformation must be documented.

Examples:

- Missing-value handling
- Column removal
- Column renaming
- Encoding
- Scaling
- Feature creation
- Sampling
- Filtering
- Deduplication
- Synthetic data generation

---

# 5. Training Data Rules

The machine-learning pipeline must prevent data leakage.

Agents must carefully distinguish:

- Training data
- Validation data
- Test data

Information from the test set must not influence model training.

---

# 6. Reproducibility

Data-processing pipelines should use deterministic configuration wherever practical.

When randomness is used:

- Define a random seed
- Record the seed
- Make the experiment reproducible

---

# 7. Dataset Sampling

Large datasets may be sampled for:

- Development
- Debugging
- Graph loading
- Local experimentation
- Demo preparation

A sample must never be confused with the complete dataset.

The documentation should state:

- Source dataset
- Sampling method
- Sample size
- Sampling seed
- Purpose

---

# 8. Neo4j Data

Do not blindly load millions of transaction records into the graph database.

Neo4j should contain data appropriate for the current prototype and graph-analysis objectives.

The graph dataset should prioritize:

- Relevant suspicious cases
- Connected accounts
- Fraud networks
- Representative transaction relationships
- Demonstration scenarios

---

# 9. Sensitive Data

Sentinel AI is a prototype.

Do not use real:

- Customer identities
- Bank credentials
- Aadhaar numbers
- PAN numbers
- Real account numbers
- Real customer addresses
- Real banking transaction records

unless explicitly authorized and appropriately protected.

Synthetic identifiers should be used for demonstrations.

---

# 10. Data in Git

Large raw datasets must not be committed to the normal source-code Git repository unless explicitly decided.

Generated artifacts should also be evaluated before committing.

The repository should contain:

- Processing logic
- Schemas
- Configuration
- Documentation
- Small test fixtures where appropriate

rather than large raw datasets.

---

# 11. AI Agent Rule

An AI agent must inspect the dataset before writing dataset-specific processing logic.

The agent must not invent column names.

The agent must verify:

- File existence
- File names
- Column names
- Data types
- Missing values
- Label fields
- Identifier relationships

before implementing the pipeline.