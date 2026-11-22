#!/usr/bin/env python3
"""Create the five demonstration cases (Phase 14).

Draws 2 fraudulent, 2 legitimate and 1 borderline transaction from the
labelled India scenarios with a fixed seed and submits each as an alert
through the same case service the API uses (store from SENTINEL_CASE_STORE).

Labels are read here ONLY to choose the transactions and to print a
comparison table; they are never stored with the case or given to the agents.
The selection does not look at the system's outcome, so the demo shows
whatever the pipeline decides, including misses.

    python scripts/seed_demo_cases.py --dry-run          # show the selection
    python scripts/seed_demo_cases.py                    # create the cases
    SENTINEL_CASE_STORE=mongodb python scripts/seed_demo_cases.py   # into Atlas
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATA_DIR = Path("dataset/processed/custom_india")
DEMO_SET = [  # (label, scenario) — two network-heavy fraud patterns, two normal, one borderline
    ("FRAUDULENT", "SCENARIO_7_LAYERING_NETWORK"),
    ("FRAUDULENT", "SCENARIO_9_FRAUD_RING_HUB"),
    ("LEGITIMATE", "SCENARIO_1_NORMAL_LEGITIMATE"),
    ("LEGITIMATE", "SCENARIO_1_NORMAL_LEGITIMATE"),
    ("BORDERLINE", "SCENARIO_12_MIXED_BORDERLINE_TRAVEL"),
]


def select(seed: int) -> list[tuple[str, str, str]]:
    import pandas as pd

    t = pd.read_csv(DATA_DIR / "transactions_targets.csv")
    out, used = [], set()
    for i, (label, scenario) in enumerate(DEMO_SET):
        pool = t[(t.risk_label == label) & (t.scenario_id == scenario) & ~t.transaction_id.isin(used)]
        row = pool.sample(n=1, random_state=seed + i).iloc[0]
        used.add(row.transaction_id)
        out.append((row.transaction_id, label, scenario))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--llm-interval", type=float, default=None,
                    help="Seconds between cases (default 60 with the LLM writer, 0 with templates)")
    a = ap.parse_args()
    try:
        from dotenv import load_dotenv

        load_dotenv(".env", override=False)
    except ImportError:
        pass
    os.environ.setdefault("SENTINEL_EVIDENCE_BACKEND", "india_synthetic")

    chosen = select(a.seed)
    if a.dry_run:
        for tx_id, label, scenario in chosen:
            print(f"{tx_id}  {label:11} {scenario}")
        return

    from src.api.case_schema import AlertRequest
    from src.api.case_store import case_store_from_env
    from src.api.service import CaseService

    llm = os.environ.get("SENTINEL_REPORT_GENERATOR", "llm").lower() != "template" and os.environ.get("GROQ_API_KEY")
    interval = a.llm_interval if a.llm_interval is not None else (60.0 if llm else 0.0)
    store = case_store_from_env()
    svc = CaseService(store)
    rows = []
    try:
        for i, (tx_id, label, scenario) in enumerate(chosen):
            if i and interval:
                time.sleep(interval)  # Groq free tier: ~1 LLM report per minute
            accepted, fut = svc.ingest(AlertRequest(transaction_id=tx_id, source_system="demo-seed"),
                                       submitted_by="demo-seed")
            if fut is not None:
                fut.result()
            rec = store.get(accepted.case_id)
            s = rec.summary
            rows.append((rec.case_id, tx_id, label, scenario, rec.status.value, s.recommended_action, s.risk_score,
                         s.report_generator, s.validation_status, "existing" if accepted.duplicate else "new"))
            print(f"{rows[-1][0]}  {tx_id}  done")
    finally:
        svc.shutdown()

    print(f"\nCase store: {store.backend_name}")
    print(f"{'Case':19} {'Transaction':22} {'Dataset label (not given to agents)':48} "
          f"{'Status':16} {'Action':12} {'Score':>6} {'Report':9} {'Validation':18}")
    for case_id, tx_id, label, scenario, status, action, score, gen, val, kind in rows:
        print(f"{case_id:19} {tx_id:22} {label + ' / ' + scenario:48} {status:16} {action or '-':12} "
              f"{'-' if score is None else f'{score:.2f}':>6} {gen or '-':9} {val or '-':18} {kind}")


if __name__ == "__main__":
    main()
