# Risk Scoring

## Purpose

Combine investigation signals into a final risk score. Implemented by Agent 4
(`src/agents/agent4/`). Configuration lives in `Agent4Config`
(`src/agents/agent4/config.py`).

## Approval status

**PROPOSED — pending project team approval** (`config_version 0.1.0-proposed`,
written 2026-11-21). These are engineering defaults for a synthetic prototype,
not regulatory thresholds. Every assessment records the version and approval
status it was produced with.

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
| OVR-LOW-COVERAGE | evidence_coverage < 0.60 | HUMAN_REVIEW |

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

## Known limitation

Agent 1 runs in `CANONICAL_MAPPED` mode for non-IEEE-CIS transactions, with
most model features imputed (`COMPATIBILITY_WARNING`). Its score is then
nearly constant across transactions, so ANOMALY contributes little
discrimination for mock / India-synthetic cases. Confidence is capped at
MEDIUM in that situation.

## Important

Risk scoring must not be hidden inside an LLM. The final score is
reproducible from `score_breakdown` and `config_snapshot` on every output.
