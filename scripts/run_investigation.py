#!/usr/bin/env python3
"""Run the Sentinel AI investigation pipeline on one India synthetic transaction.

Usage:
    PYTHONPATH=. python scripts/run_investigation.py TXN_IND_202608_000123 [--json] [--template]
        [--no-report] [--report-out FILE.md]

Uses the India synthetic evidence backend and the local Neo4j graph
(NEO4J_* in .env). Ground-truth labels are never given to the agents; the
script prints the dataset label separately, for comparison only.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATA_DIR = Path("dataset/processed/custom_india")


def load_row(tx_id: str) -> tuple[dict, dict]:
    import pandas as pd

    f = pd.read_csv(DATA_DIR / "transactions_features.csv")
    row = f[f["transaction_id"] == tx_id]
    if row.empty:
        raise SystemExit(f"Transaction {tx_id} not found in {DATA_DIR}")
    t = pd.read_csv(DATA_DIR / "transactions_targets.csv")
    label = t[t["transaction_id"] == tx_id].iloc[0].to_dict()
    return row.iloc[0].to_dict(), label


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("transaction_id")
    ap.add_argument("--json", action="store_true", help="Print the full Agent 4 output as JSON")
    ap.add_argument("--template", action="store_true", help="Use the template report writer (no LLM call)")
    ap.add_argument("--no-report", action="store_true", help="Stop after Agent 4")
    ap.add_argument("--report-out", default=None, help="Write the Markdown report to this file")
    a = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except ImportError:
        pass
    os.environ.setdefault("SENTINEL_EVIDENCE_BACKEND", "india_synthetic")
    os.environ.setdefault("SENTINEL_NEWS_PROVIDER", "mock")
    if a.template:
        os.environ["SENTINEL_REPORT_GENERATOR"] = "template"

    from src.agents.investigation import Investigator
    from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

    row, label = load_row(a.transaction_id)
    tx = IndiaSyntheticAdapter.from_row(row)  # features only; labels are not passed in
    with Investigator(generate_report=not a.no_report) as inv:
        state = inv.investigate(tx)

    a1, a2, a3, a4 = (state[k] for k in ("agent1_output", "agent2_output", "agent3_output", "agent4_output"))
    if a.json:
        print(a4.model_dump_json(indent=2))
        return
    print(f"Case {state['case_id']}  transaction {tx.raw_record_id}")
    print(f"  {tx.amount} {tx.currency} {tx.channel} {tx.sender.account_id} -> {tx.receiver.account_id} at {tx.timestamp}")
    print(f"Agent 1  {a1.status.value:22} combined_confidence={a1.combined_confidence}")
    print(f"Agent 2  {a2.status.value:22} failed={a2.failed_providers}")
    print(f"Agent 3  {a3.status.value:22} findings={[f.pattern_type.value for f in a3.findings]}")
    print(f"Agent 4  {a4.status.value:22} score={a4.risk_score} action={a4.recommended_action.value} "
          f"confidence={a4.confidence.value} SAR={a4.sar_recommendation.recommended}")
    for b in a4.score_breakdown:
        v = "n/a" if b.value is None else f"{b.value:.2f}"
        print(f"    {b.signal.value:17} w={b.weight:.2f} v={v:>5}  {b.rationale[:90]}")
    if a4.overrides_applied:
        print("  overrides:", [o.rule_id for o in a4.overrides_applied])
    print("  regulatory:", sorted({m.reference_id for m in a4.regulatory_matches}))
    print("  unmapped:", [u.value for u in a4.unmapped_triggers])
    a5 = state.get("agent5_output")
    if a5 is not None:
        from src.agents.agent5 import render_markdown
        print(f"Agent 5  {a5.status.value:22} generator={a5.generator.value if a5.generator else None} "
              f"model={a5.llm_model} facts={len(a5.evidence_bundle.facts) if a5.evidence_bundle else 0} "
              f"validation={a5.validation_status}")
        if a5.fallback_reason:
            print(f"  LLM not used: {a5.fallback_reason}")
        v = state.get("validation_output")
        if v is not None:
            print(f"Validator {v.status.value:21} checks {v.checks_passed}/{v.checks_total}"
                  + (f" failed={[c.value for c in v.failed_checks()]}" if v.failed_checks() else ""))
        for rr in state.get("rejected_reports") or []:
            print(f"  rejected report kept for audit: {rr.reason}")
        md = render_markdown(a5, validation=state.get("validation_output"))
        if a.report_out:
            Path(a.report_out).write_text(md)
            print(f"  report written to {a.report_out}")
        else:
            print("\n" + md)
    print(f"Dataset label (NOT given to agents): {label['risk_label']} / {label['scenario_id']}")


if __name__ == "__main__":
    main()
