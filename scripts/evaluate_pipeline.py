#!/usr/bin/env python3
"""Evaluate Agents 1–4 end to end on labelled India synthetic transactions.

Runs the investigation pipeline on a stratified sample (labels are NOT given
to the agents; they are joined afterwards for evaluation only) and reports:
  * recommended action × dataset risk label
  * per-scenario mean risk score and action distribution
  * how often each signal / network pattern fired per label

Usage:
    PYTHONPATH=. python scripts/evaluate_pipeline.py [--per-scenario 25] [--normal 300] [--out FILE]
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
DATA_DIR = Path("dataset/processed/custom_india")
NORMAL = "SCENARIO_1_NORMAL_LEGITIMATE"
ACTIONS = ["CLEAR", "MONITOR", "HUMAN_REVIEW", "ESCALATE", "BLOCK"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-scenario", type=int, default=25)
    ap.add_argument("--normal", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None, help="Write full results JSON here")
    a = ap.parse_args()

    logging.basicConfig(level=logging.ERROR)
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except ImportError:
        pass
    os.environ.setdefault("SENTINEL_EVIDENCE_BACKEND", "india_synthetic")
    os.environ["SENTINEL_NEWS_PROVIDER"] = "mock"

    import pandas as pd

    from src.agents.investigation import Investigator
    from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

    feats = pd.read_csv(DATA_DIR / "transactions_features.csv")
    labels = pd.read_csv(DATA_DIR / "transactions_targets.csv")
    m = feats.merge(labels[["transaction_id", "risk_label", "scenario_id"]], on="transaction_id")
    parts = []
    for sc, g in m.groupby("scenario_id"):
        n = a.normal if sc == NORMAL else a.per_scenario
        parts.append(g.sample(min(n, len(g)), random_state=a.seed))
    sample = pd.concat(parts)

    rows = []
    t0 = time.time()
    with Investigator(generate_report=False) as inv:
        for rec in sample.to_dict("records"):
            tx = IndiaSyntheticAdapter.from_row({k: rec[k] for k in feats.columns})
            st = inv.investigate(tx)
            o = st["agent4_output"]
            rows.append({
                "transaction_id": rec["transaction_id"],
                "risk_label": rec["risk_label"],
                "scenario_id": rec["scenario_id"],
                "risk_score": o.risk_score,
                "action": o.recommended_action.value,
                "confidence": o.confidence.value,
                "sar": o.sar_recommendation.recommended,
                "signals": {b.signal.value: b.value for b in o.score_breakdown},
                "patterns": sorted({f.pattern_type.value for f in st["agent3_output"].findings}),
                "agent_status": [st[k].status.value for k in ("agent1_output", "agent2_output", "agent3_output")],
            })
    elapsed = time.time() - t0
    df = pd.DataFrame(rows)

    print(f"\n{len(df)} cases in {elapsed:.0f}s ({elapsed / len(df):.2f}s/case)\n")
    ct = pd.crosstab(df["risk_label"], df["action"]).reindex(columns=[c for c in ACTIONS if c in set(df["action"])])
    print("Recommended action × dataset label (counts)")
    print(ct.to_string(), "\n")
    print("Row %")
    print((ct.div(ct.sum(axis=1), axis=0) * 100).round(1).to_string(), "\n")

    print("Per scenario: mean score, % ESCALATE+BLOCK, % SAR")
    per = df.groupby("scenario_id").agg(
        n=("risk_score", "size"),
        mean_score=("risk_score", "mean"),
        escalate_or_block=("action", lambda s: (s.isin(["ESCALATE", "BLOCK"])).mean() * 100),
        sar=("sar", lambda s: s.mean() * 100),
    ).round(1)
    print(per.to_string(), "\n")

    print("Signal firing rate (value >= 0.5) by label, %")
    sig = pd.DataFrame([{k: (v is not None and v >= 0.5) for k, v in r.items()} for r in df["signals"]])
    sig["risk_label"] = df["risk_label"].values
    print((sig.groupby("risk_label").mean() * 100).round(1).T.to_string(), "\n")

    pat = collections.defaultdict(collections.Counter)
    for lbl, ps in zip(df["risk_label"], df["patterns"]):
        for p in ps:
            pat[lbl][p] += 1
    n_by = df["risk_label"].value_counts().to_dict()
    print("Network pattern rate by label, %")
    for lbl in sorted(pat):
        print(f"  {lbl:11}", {p: round(100 * c / n_by[lbl], 1) for p, c in pat[lbl].most_common()})

    statuses = collections.Counter(s for ss in df["agent_status"] for s in ss)
    print("\nUpstream agent statuses:", dict(statuses))

    if a.out:
        Path(a.out).write_text(json.dumps({
            "n": len(df), "seconds": round(elapsed, 1),
            "crosstab": ct.to_dict(), "per_scenario": per.to_dict(orient="index"),
            "cases": rows,
        }, indent=2, default=str))
        print(f"\nWrote {a.out}")


if __name__ == "__main__":
    main()
