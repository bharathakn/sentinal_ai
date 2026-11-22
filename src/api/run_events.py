"""
Sentinel AI — what the live view shows for each finished pipeline node.

Every value is copied from that node's own output. Nothing is computed,
estimated or invented for the animation.
"""

from __future__ import annotations

from typing import Any

from ..agents.pipeline_graph import NodeName as N
from .network_view import network_from_outputs

PROVIDERS = ("core_banking", "kyc", "device", "beneficiary", "sanctions_subject", "sanctions_account",
             "geolocation", "news")


def _dump(obj: Any) -> dict:
    return obj.model_dump(mode="json") if obj is not None else {}


def _pick(d: dict, *keys: str) -> dict:
    return {k: d.get(k) for k in keys}


def node_view(node: N, state: dict, update: dict) -> dict[str, Any]:
    if node == N.ANOMALY_DETECTOR and "agent1_output" in update:
        a1 = _dump(update["agent1_output"])
        xgb, iso = a1.get("xgboost_detail") or {}, a1.get("isolation_forest_detail") or {}
        return {**_pick(a1, "status", "combined_confidence", "warnings"),
                "xgboost": _pick(xgb, "fraud_probability", "threshold_used", "is_fraud_predicted"),
                "isolation_forest": _pick(iso, "anomaly_score", "threshold_used", "is_anomaly"),
                "drivers": (a1.get("top_deviation_features") or [])[:6]}
    if node == N.EVIDENCE_GATHERER and "agent2_output" in update:
        a2 = _dump(update["agent2_output"])
        providers = [{"name": key, **_pick(value, "source", "source_mode", "status")}
                     for key, value in a2.items()
                     if isinstance(value, dict) and "source" in value and "status" in value]
        answered = {p["name"] for p in providers}
        # A provider that gave no response still appears, as unavailable.
        providers += [{"name": r["provider_name"], "source": None, "source_mode": None, "status": r["status"],
                       "error": r.get("error_summary")}
                      for r in a2.get("provider_results") or []
                      if r.get("status") in ("PROVIDER_ERROR", "VALIDATION_ERROR")
                      and r["provider_name"].lower() not in answered]
        order = {name: i for i, name in enumerate(PROVIDERS)}
        providers.sort(key=lambda p: order.get(p["name"], len(order)))
        return {**_pick(a2, "status", "warnings"), "providers": providers}
    if node == N.NETWORK_ANALYSER and "agent3_output" in update:
        return network_from_outputs(state.get("case_id"), _dump(update["agent3_output"]),
                                    _dump(state.get("transaction")))
    if node == N.RISK_ASSESSOR and "agent4_output" in update:
        a4 = _dump(update["agent4_output"])
        view = _pick(a4, "status", "risk_score", "score_band_action", "recommended_action", "confidence",
                     "evidence_coverage", "unavailable_signals", "overrides_applied", "sar_recommendation")
        view["thresholds"] = _pick(a4.get("config_snapshot") or {}, "monitor_threshold", "escalate_threshold",
                                   "block_threshold")
        view["signals"] = [_pick(s, "signal", "weight", "value", "available", "contribution", "rationale")
                           for s in a4.get("score_breakdown") or []]
        return view
    if node == N.EXPLANATION_GENERATOR and "agent5_output" in update:
        a5 = _dump(update["agent5_output"])
        # A draft: the validator has not seen it yet, and the UI must say so.
        return {**_pick(a5, "status", "generator", "llm_model", "fallback_reason", "validation_status"),
                "sections": [{"title": s["title"],
                              "statements": [_pick(x, "text", "fact_ids", "origin") for x in s["statements"]]}
                             for s in a5.get("sections") or [] if s["section"] != "SOURCE_AUDIT_TRAIL"]}
    if node == N.OUTPUT_VALIDATOR and "validation_output" in update:
        v = _dump(update["validation_output"])
        presented = _dump(update.get("agent5_output"))
        rejected = [_dump(r) for r in update.get("rejected_reports") or []]
        return {**_pick(v, "status", "checks_passed", "checks_total"),
                "checks": [{**_pick(c, "check", "description", "passed", "items_checked"),
                            "issues": [i["reason"] for i in c["issues"]][:5]} for c in v.get("checks") or []],
                "rejected": [{"reason": r.get("reason"),
                              "issues": [i["reason"] for c in r["validation"]["checks"] for i in c["issues"]][:5]}
                             for r in rejected],
                "presented_generator": presented.get("generator"),
                "sections": [{"title": s["title"],
                              "statements": [_pick(x, "text", "fact_ids", "origin") for x in s["statements"]]}
                             for s in presented.get("sections") or [] if s["section"] != "SOURCE_AUDIT_TRAIL"]
                if rejected else None}
    return {}
