"""Phase 14 — network view built from stored Agent 3 findings, and demo-case selection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.api.case_schema import AlertInfo, AlertSource, CaseRecord, CaseStatus, utcnow
from src.api.network_view import MAX_EDGES, build_network_view


def _t(rid, a, b, amt=100.0, gid=None):
    return {"tx_graph_id": gid, "raw_record_id": rid, "from_account_id": a, "to_account_id": b, "amount": amt,
            "currency": "INR", "timestamp_utc": "2026-08-01T00:00:00Z", "channel": "UPI"}


def _case(findings, status="COMPLETE"):
    now = utcnow()
    return CaseRecord(
        case_id="CASE-N", transaction_key="k", status=CaseStatus.AWAITING_REVIEW, created_at_utc=now, updated_at_utc=now,
        alert=AlertInfo(source=AlertSource.API, received_at_utc=now),
        transaction={"raw_record_id": "T0", "amount": "500.00", "currency": "INR", "timestamp": "2026-08-01T10:00:00+05:30",
                     "channel": "NEFT", "sender": {"account_id": "A"}, "receiver": {"account_id": "B"}},
        investigation={"agent3_output": {"status": status, "findings": findings, "warnings": []}},
    )


def _finding(fid, ptype, subject, related=(), transfers=(), paths=()):
    return {"finding_id": fid, "pattern_type": ptype, "rule_id": f"AGENT3.{ptype}.v2", "subject_account_id": subject,
            "related_account_ids": list(related), "supporting_transfers": list(transfers),
            "layering_paths": [{"account_ids": [], "hop_count": len(p), "transfers": list(p)} for p in paths],
            "heuristic_score": 0.9, "transfer_count": None, "total_amount": None, "currency": "INR",
            "elapsed_minutes": None, "explanation": f"{ptype} explanation"}


def test_no_findings_shows_only_investigated_transfer():
    v = build_network_view(_case([]))
    assert {n["id"]: n["roles"] for n in v["nodes"]} == {"A": ["SENDER"], "B": ["RECEIVER"]}
    assert len(v["edges"]) == 1 and v["edges"][0]["investigated"] is True and v["edges"][0]["patterns"] == []
    assert v["findings"] == [] and "not conclusions" in v["note"]


def test_findings_merge_with_investigated_transfer_and_roles():
    f1 = _finding("f1", "LAYERING", "A", related=["B", "C", "D"],
                  paths=[[_t("T0", "A", "B", 500.0, gid="g0"), _t("T1", "B", "C"), _t("T2", "C", "D")]])
    f2 = _finding("f2", "RAPID_FORWARDING", "B", related=["C"], transfers=[_t("T1", "B", "C", gid="g1")])
    v = build_network_view(_case([f1, f2]))
    edges = {e["id"]: e for e in v["edges"]}
    assert set(edges) == {"T0", "T1", "T2"}                      # same transfer never drawn twice
    assert edges["T0"]["investigated"] and edges["T0"]["patterns"] == ["LAYERING"]
    assert edges["T1"]["finding_ids"] == ["f1", "f2"]
    nodes = {n["id"]: n for n in v["nodes"]}
    assert nodes["A"]["roles"] == ["SENDER", "SUBJECT"]
    assert set(nodes["C"]["patterns"]) == {"LAYERING", "RAPID_FORWARDING"}
    assert [f["pattern_type"] for f in v["findings"]] == ["LAYERING", "RAPID_FORWARDING"]


def test_only_stored_relationships_are_drawn():
    f = _finding("f1", "FAN_OUT", "B", related=["X"], transfers=[_t("T9", "B", "X"), {"raw_record_id": "bad"}])
    v = build_network_view(_case([f]))
    pairs = {(e["source"], e["target"]) for e in v["edges"]}
    assert pairs == {("A", "B"), ("B", "X")}  # transfers without both ends are skipped, nothing inferred


def test_truncation_keeps_investigated_and_finding_edges():
    many = [_t(f"S{i}", "B", f"Z{i}") for i in range(MAX_EDGES + 50)]
    v = build_network_view(_case([_finding("f1", "FAN_OUT", "B", transfers=many)]))
    assert v["truncated"] and len(v["edges"]) == MAX_EDGES and v["total_edges"] == MAX_EDGES + 51
    assert any(e["investigated"] for e in v["edges"])


def test_no_investigation_yet():
    now = utcnow()
    rec = CaseRecord(case_id="C", transaction_key="k", status=CaseStatus.RECEIVED, created_at_utc=now,
                     updated_at_utc=now, alert=AlertInfo(source=AlertSource.API, received_at_utc=now), transaction={})
    assert build_network_view(rec) is None


DATA = Path("dataset/processed/custom_india/transactions_targets.csv")


@pytest.mark.skipif(not DATA.exists(), reason="India dataset not built")
def test_demo_selection_is_deterministic_and_balanced():
    spec = importlib.util.spec_from_file_location("seed_demo", "scripts/seed_demo_cases.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a, b = mod.select(14), mod.select(14)
    assert a == b and len({t for t, _, _ in a}) == 5
    labels = [label for _, label, _ in a]
    assert labels.count("FRAUDULENT") == 2 and labels.count("LEGITIMATE") == 2 and labels.count("BORDERLINE") == 1
