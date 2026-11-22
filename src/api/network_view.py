"""
Sentinel AI — Phase 14: account-network view of a case.

Builds the graph the dashboard draws from the case's **stored Agent 3
output** (findings, supporting transfers, layering paths) plus the
investigated transaction. Neo4j is not queried, so the picture is exactly the
evidence the investigation used and stays reproducible after the graph
changes. No relationship is added that the stored evidence does not contain.
"""

from __future__ import annotations

from typing import Any, Optional

from .case_schema import CaseRecord

MAX_EDGES = 300
NOTE = ("Accounts and transfers cited by Agent 3 network findings (stored with the case), plus the "
        "investigated transaction. Network findings are heuristic patterns for analyst review, not "
        "conclusions.")


def _edge_key(t: dict) -> str:
    return (t.get("raw_record_id") or t.get("tx_graph_id")
            or f"{t.get('from_account_id')}>{t.get('to_account_id')}@{t.get('timestamp_utc')}")


def build_network_view(case: CaseRecord) -> Optional[dict[str, Any]]:
    a3 = (case.investigation or {}).get("agent3_output")
    if a3 is None:
        return None
    return network_from_outputs(case.case_id, a3, case.transaction or {})


def network_from_outputs(case_id: Optional[str], a3: dict, tx: dict) -> dict[str, Any]:
    """The view from a JSON-mode Agent 3 output and transaction."""
    sender = (tx.get("sender") or {}).get("account_id")
    receiver = (tx.get("receiver") or {}).get("account_id")
    tx_id = tx.get("raw_record_id")

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def node(acc: Optional[str], role: Optional[str] = None, finding: Optional[dict] = None) -> None:
        if not acc:
            return
        n = nodes.setdefault(acc, {"id": acc, "roles": [], "finding_ids": [], "patterns": []})
        if role and role not in n["roles"]:
            n["roles"].append(role)
        if finding:
            if finding["finding_id"] not in n["finding_ids"]:
                n["finding_ids"].append(finding["finding_id"])
            if finding["pattern_type"] not in n["patterns"]:
                n["patterns"].append(finding["pattern_type"])

    def edge(t: dict, finding: Optional[dict] = None) -> None:
        src, dst = t.get("from_account_id"), t.get("to_account_id")
        if not (src and dst):
            return
        key = _edge_key(t)
        e = edges.get(key)
        if e is None:
            e = edges[key] = {
                "id": key, "source": src, "target": dst, "raw_record_id": t.get("raw_record_id"),
                "amount": t.get("amount"), "amount_str": t.get("amount_str"), "currency": t.get("currency"),
                "timestamp_utc": t.get("timestamp_utc"), "channel": t.get("channel"),
                "investigated": bool(tx_id and t.get("raw_record_id") == tx_id),
                "finding_ids": [], "patterns": [],
            }
        node(src, finding=finding)
        node(dst, finding=finding)
        if finding:
            if finding["finding_id"] not in e["finding_ids"]:
                e["finding_ids"].append(finding["finding_id"])
            if finding["pattern_type"] not in e["patterns"]:
                e["patterns"].append(finding["pattern_type"])

    node(sender, "SENDER")
    node(receiver, "RECEIVER")
    if sender and receiver:
        edge({"raw_record_id": tx_id, "from_account_id": sender, "to_account_id": receiver,
              "amount": float(tx["amount"]) if tx.get("amount") is not None else None,
              "amount_str": str(tx.get("amount")) if tx.get("amount") is not None else None,
              "currency": tx.get("currency"), "timestamp_utc": tx.get("timestamp"), "channel": tx.get("channel")})

    findings = []
    for f in a3.get("findings") or []:
        node(f.get("subject_account_id"), "SUBJECT", f)
        for acc in f.get("related_account_ids") or []:
            node(acc, "RELATED", f)
        for t in f.get("supporting_transfers") or []:
            edge(t, f)
        for p in f.get("layering_paths") or []:
            for t in p.get("transfers") or []:
                edge(t, f)
        findings.append({k: f.get(k) for k in ("finding_id", "pattern_type", "rule_id", "subject_account_id",
                                               "related_account_ids", "heuristic_score", "transfer_count",
                                               "total_amount", "currency", "elapsed_minutes", "explanation")})

    all_edges = list(edges.values())
    # Keep the investigated transaction and finding-linked transfers first if trimming.
    all_edges.sort(key=lambda e: (not e["investigated"], -len(e["finding_ids"])))
    kept = all_edges[:MAX_EDGES]
    used = {e["source"] for e in kept} | {e["target"] for e in kept}
    kept_nodes = [n for n in nodes.values() if n["id"] in used or n["roles"]]
    return {
        "case_id": case_id,
        "agent3_status": a3.get("status"),
        "sender_account_id": sender,
        "receiver_account_id": receiver,
        "nodes": kept_nodes,
        "edges": kept,
        "findings": findings,
        "truncated": len(all_edges) > MAX_EDGES,
        "total_edges": len(all_edges),
        "source": "AGENT_3 stored output",
        "agent3_warnings": a3.get("warnings") or [],
        "note": NOTE,
    }


__all__ = ["build_network_view", "MAX_EDGES"]
