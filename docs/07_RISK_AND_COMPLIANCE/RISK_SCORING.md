# Risk Scoring

## Purpose

Combine investigation signals into a final risk score. Implemented by Agent 4
(`src/agents/agent4/`). Configuration lives in `Agent4Config`
(`src/agents/agent4/config.py`).

## Approval status

**APPROVED 2026-11-21** (`config_version 1.0.0`; decision delegated by the
project owner). Calibrated on SYNTHETIC data; these are prototype policy
values, not regulatory thresholds, and must be re-approved before use on real
data. Every assessment records the version and approval status it was
produced with. 1.0.0 = 0.1.0-proposed weights and bands + `OVR-HIGH-ANOMALY`.

## Weights

| Signal | Weight | Rationale |
|---|---|---|
| ANOMALY | 0.30 | Strongest measured signal (XGBoost ROC-AUC 0.934) |
| NETWORK_RISK | 0.20 | Graph typologies invisible to single-transaction models |
| SANCTIONS_HIT | 0.15 | Also enforced by a hard override, so the weight only shapes the score |
| NEW_BENEFICIARY | 0.10 | Authorised-push-payment / mule indicator |
| NEW_DEVICE | 0.10 | Account-takeover indicator |
| LOCATION_ANOMALY | 0.10 | Account-takeover / travel indicator; noisier |
| UNUSUAL_TIMING | 0.05 | Weakest standalone signal |

Weights must cover all seven signals and sum to 1.0 (validated).

## Calculation

```
evidence_coverage = Σ weight(available signals)
risk_score        = 100 × Σ weight × value (available) / evidence_coverage
```

Unavailable signals are excluded and reduce `evidence_coverage` (and
confidence). They are never scored as 0.

## Action bands

| risk_score | Band action |
|---|---|
| < 25 | CLEAR |
| 25 – < 50 | MONITOR |
| 50 – < 75 | ESCALATE |
| ≥ 75 | BLOCK |

## Overrides

Overrides only raise the action (severity: CLEAR < MONITOR < HUMAN_REVIEW <
ESCALATE < BLOCK).

| Rule | Condition | Minimum action |
|---|---|---|
| OVR-SANCTIONS-MATCH | any sanctions screen MATCH_FOUND | BLOCK |
| OVR-SANCTIONS-UNAVAILABLE | an attempted screen failed (provider/auth error) or no screen completed | HUMAN_REVIEW |
| OVR-HIGH-ANOMALY | ANOMALY signal ≥ 0.70 (`high_anomaly_review_threshold`) | HUMAN_REVIEW |
| OVR-LOW-COVERAGE | evidence_coverage < 0.60 | HUMAN_REVIEW |

**Why OVR-HIGH-ANOMALY.** Under 0.1.0, a payment 8–15× the customer's normal
amount to an established payee only fired ANOMALY (weight 0.30), so it could
never leave MONITOR. A model score alone is not grounds for escalation or a
SAR, but a strong one must reach an analyst. The rule sends it to
HUMAN_REVIEW (below ESCALATE, so no SAR). Threshold chosen from the Phase 9.5
evaluation: ANOMALY ≥ 0.70 in 96% of high-value spikes and 0.3% of legitimate
transactions (legitimate 99th percentile 0.43).

A screen not attempted because the identifier was missing (Agent 2
`VALIDATION_ERROR`) is reported as a warning, not a failure, as long as the
other screen completed.

## SAR / STR recommendation

Recommended when the final action is ESCALATE or BLOCK. The `basis` lists
the score band and/or override rule ids. It is a system recommendation
requiring qualified human review, never a filing.

## Confidence

| Level | Condition |
|---|---|
| HIGH | coverage ≥ 0.90 and Agents 1–3 all COMPLETE |
| MEDIUM | coverage ≥ 0.60 |
| LOW | coverage < 0.60 |

## Signal parameters

| Parameter | Default |
|---|---|
| Night window (local time of the transaction timestamp) | 23:00–05:59 |
| Recent beneficiary (payment within N minutes of adding) | 60 min |
| Young beneficiary account (partial 0.5 signal) | < 30 days |
| Default value for an Agent 3 finding with no heuristic score | 0.5 |
| Signal value that raises a regulatory trigger | ≥ 0.5 |

## Signal notes

- NEW_BENEFICIARY relationship novelty comes from the sender's side
  (transaction flag; sender's known beneficiaries). The beneficiary record adds
  beneficiary risk (prior fraud flag → 1.0; account younger than 30 days →
  0.5). The beneficiary's own transaction count is not used.

## Evaluation (Phase 9.5, config 1.0.0)

`scripts/evaluate_pipeline.py` ran Agents 1–4 on 575 labelled India v2
transactions (300 legitimate + 25 per suspicious scenario). Labels were joined
only after the agents ran. All 1,725 upstream agent runs were COMPLETE.

| Dataset label | CLEAR | MONITOR | HUMAN_REVIEW | ESCALATE | BLOCK |
|---|---|---|---|---|---|
| LEGITIMATE (300) | 86.7% | 13.0% | 0.3% | 0.0% | 0.0% |
| FRAUDULENT (194) | 0.0% | 5.7% | 11.3% | 81.4% | 1.5% |
| BORDERLINE (81) | 8.6% | 25.9% | 30.9% | 34.6% | 0.0% |

(0.1.0 for comparison: FRAUDULENT 3.1% CLEAR / 13.9% MONITOR; no HUMAN_REVIEW.)

| Scenario | Mean score | HUMAN_REVIEW | ESCALATE/BLOCK |
|---|---|---|---|
| Normal | 13.2 | 0% | 0% |
| High-value spike | 27.9 | **96%** | 0% |
| Borderline travel | 34.1 | 28% | 20% |
| Impossible travel / New beneficiary large | ~51 | 20–32% | 60% |
| Mule / Ring | 54–56 | 0% | 84% |
| Rapid burst / Structuring / Layering / New device / Shared device | 60–64 | 0–8% | 76–100% |

Observations:

1. No legitimate case reached ESCALATE or BLOCK (no SAR); 1 of 300 reached
   HUMAN_REVIEW via OVR-HIGH-ANOMALY.
2. No fraudulent case is CLEARed; high-value spikes reach an analyst but do
   not produce a SAR recommendation on the model score alone.
3. BLOCK is reached only via score ≥ 75 or a sanctions match; the India
   dataset contains no sanctions matches.
4. Results are on SYNTHETIC data and are not real-world performance.

## Important

Risk scoring must not be hidden inside an LLM. The final score is
reproducible from `score_breakdown` and `config_snapshot` on every output.
