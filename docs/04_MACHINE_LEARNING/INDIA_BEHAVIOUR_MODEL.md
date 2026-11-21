# India Behavioural Model (Agent 1, Phase 9.5)

## Why

The IEEE-CIS models score India transactions with ~430 of ~434 features
imputed, so their output is near-constant for India cases (0.219 for both a
normal and a suspicious case in the Phase 9 smoke run). Agent 1 now routes
`INDIA_SYNTHETIC` transactions to a model trained on India behavioural
features (`ScoringMode.INDIA_NATIVE`). IEEE-CIS transactions keep the IEEE-CIS
models.

## Code

| File | Purpose |
|---|---|
| `src/ml/india_behaviour_model.py` | Feature extraction, training, `IndiaBehaviourScorer` |
| `scripts/train_india_model.py` | Training CLI → `models/india_behaviour/v1/` (git-ignored) |
| `src/agents/agent1/anomaly_detector.py` | Routing (`_score_india`); falls back to IEEE-CIS mapping with a warning if artifacts are missing |

## Features (12)

`log_amount`, `amount_ratio_vs_30d_avg`, `log_amount_ratio`,
`tx_frequency_24h`, `log_time_since_last_tx`, `balance_drain_ratio`,
`hour_of_day`, `is_night`, `day_of_week`, `channel_upi/neft/rtgs`.

Extracted from `CanonicalTransaction` by the same function in training and
scoring (train/serve parity). **Excluded** because Agent 4 scores them as
separate signals (avoids double counting): `is_new_device`,
`is_new_beneficiary`, `distance_from_home_km`,
`time_since_beneficiary_added_min`.

## Training

- Label: `is_fraud` (BORDERLINE counted as 0), read only by the trainer.
- Stratified 70/15/15 train/validation/test, seed 42.
- XGBoost (300 trees, depth 4, class weighting); Isolation Forest (200 trees, median-imputed).
- Thresholds: F1-max on validation. Test evaluated once.

## Results (dataset v2.0.0, test split n = 1,500, 201 positives)

| Model | Threshold | ROC-AUC | PR-AUC | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|
| XGBoost | 0.721 | 0.972 | 0.853 | 0.744 | 0.826 | 0.783 | 0.044 |
| Isolation Forest | 0.527 | 0.844 | 0.599 | 0.588 | 0.517 | 0.550 | 0.056 |

combined_confidence uses the existing 70/30 strategy, with the IF sigmoid
centred on the India IF threshold.

> **Caveat:** labels are SYNTHETIC, produced by a rule-based generator. These
> metrics are optimistic and are not comparable with real-world fraud detection.
