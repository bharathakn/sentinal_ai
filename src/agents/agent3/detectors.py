"""
Sentinel AI — Agent 3: Network Pattern Detectors

Implements the seven network-pattern detectors used by Agent 3. Each
detector is a standalone function that accepts raw Cypher result rows and
an Agent3Config, and returns zero or more NetworkFinding objects.

All thresholds are read from Agent3Config — never hardcoded locally.

Rules
-----
* Detectors operate on graph query results (dicts). They do NOT query Neo4j
  themselves. The query is performed by NetworkAnalyserAgent; the detector
  receives the results.
* A positive finding must be backed by actual graph data in the result rows.
* An empty return means the check completed and found nothing — not a failure.
* Missing timestamps are handled explicitly (no silent ordering invented).
* No detector produces a final fraud determination or risk score.
* Heuristic scores in [0, 1] are labelled as prototype signals.

Rule version v2 (Phase 9.5)
---------------------------
v1 rules were timeless and structural (e.g. "≥3 recipients ever"); on a
realistically dense graph every account matched. v2 rules are temporal:
counts are taken within sliding time windows, chains must be time-ordered
with amount continuity, and clusters are time-ordered cycles. The analyser
passes only rows inside the analysis window around the investigated
transaction.

Design pattern
--------------
Each public detector function has the signature:

    def detect_<pattern>(
        graph_rows:  dict[str, list[dict]],
        subject_id:  str,
        config:      Agent3Config,
    ) -> list[NetworkFinding]:

`graph_rows` is the account's raw transfer data keyed by "incoming" /
"outgoing" / "paths". The caller (NetworkAnalyserAgent) fetches the data
and passes it in.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import Agent3Config
from .output_schema import (
    LayeringPath,
    NetworkFinding,
    NetworkPatternType,
    TransferRef,
)

logger = logging.getLogger(__name__)

_RULE_VERSION = "v2"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse a UTC ISO-8601 string stored in the graph. Returns None on failure."""
    if not ts_str:
        return None
    try:
        # Handle both with and without timezone suffix
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, TypeError):
        return None


def _elapsed_minutes(ts_a: Optional[str], ts_b: Optional[str]) -> Optional[float]:
    """Return elapsed minutes between two UTC ISO timestamp strings, or None."""
    dt_a = _parse_ts(ts_a)
    dt_b = _parse_ts(ts_b)
    if dt_a is None or dt_b is None:
        return None
    return (dt_b - dt_a).total_seconds() / 60.0


def _elapsed_hours(ts_a: Optional[str], ts_b: Optional[str]) -> Optional[float]:
    mins = _elapsed_minutes(ts_a, ts_b)
    return mins / 60.0 if mins is not None else None


def _row_to_transfer_ref(
    row: dict,
    from_id: Optional[str] = None,
    to_id: Optional[str] = None,
) -> TransferRef:
    """Convert a Cypher result row into a TransferRef."""
    return TransferRef(
        tx_graph_id=row.get("tx_graph_id"),
        raw_record_id=row.get("raw_record_id"),
        from_account_id=from_id or row.get("account_id"),
        to_account_id=to_id or row.get("counterpart_id"),
        amount=row.get("amount"),
        amount_str=row.get("amount_str"),
        currency=row.get("currency"),
        timestamp_utc=row.get("timestamp_utc"),
        channel=row.get("channel"),
    )


def _total_amount(rows: list[dict]) -> Optional[float]:
    amounts = [r["amount"] for r in rows if r.get("amount") is not None]
    return sum(amounts) if amounts else None


def _dominant_currency(rows: list[dict]) -> Optional[str]:
    currencies = [r["currency"] for r in rows if r.get("currency")]
    if not currencies:
        return None
    return max(set(currencies), key=currencies.count)



def _ts_sorted(rows: list[dict]) -> list[tuple[dict, datetime]]:
    """Rows with a parseable timestamp, oldest first (rows without are dropped)."""
    out = [(r, _parse_ts(r.get("timestamp_utc"))) for r in rows]
    out = [(r, t) for r, t in out if t is not None]
    out.sort(key=lambda x: x[1])
    return out


def _best_window(
    rows: list[tuple[dict, datetime]], window_secs: float, key: str
) -> list[tuple[dict, datetime]]:
    """Window (≤ window_secs) containing the most distinct values of `key`."""
    best: list[tuple[dict, datetime]] = []
    best_n = 0
    j = 0
    for i in range(len(rows)):
        while rows[i][1].timestamp() - rows[j][1].timestamp() > window_secs:
            j += 1
        group = rows[j: i + 1]
        n = len({r.get(key) for r, _ in group if r.get(key)})
        if n > best_n:
            best_n, best = n, group
    return best


# ---------------------------------------------------------------------------
# Detector A: Layering (time-ordered chain with amount continuity)
# ---------------------------------------------------------------------------

def _valid_chain(transfers: list[dict], config: Agent3Config) -> tuple[bool, Optional[float]]:
    """Check time order, per-hop gap, amount retention and total elapsed."""
    times = [_parse_ts(t.get("timestamp_utc")) for t in transfers]
    if any(t is None for t in times):
        return False, None
    max_gap = config.layering_hop_max_gap_hours * 3600
    for i in range(1, len(transfers)):
        gap = (times[i] - times[i - 1]).total_seconds()
        if gap <= 0 or gap > max_gap:
            return False, None
        prev_amt, amt = transfers[i - 1].get("amount"), transfers[i].get("amount")
        if prev_amt is None or amt is None or amt < config.layering_min_amount_retention * prev_amt:
            return False, None
    elapsed_h = (times[-1] - times[0]).total_seconds() / 3600
    if elapsed_h > config.layering_max_elapsed_hours:
        return False, None
    return True, elapsed_h


def detect_layering(
    paths: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect layering — a time-ordered chain of transfers through intermediaries.

    Detection rule: AGENT3.LAYERING.v2
    ``paths`` are candidate chains ({node_ids, transfers}) through the
    investigated transfer. A chain is flagged when ALL hold:
      * hop count ≥ min_layering_hops
      * every timestamp present and strictly increasing
      * each hop within layering_hop_max_gap_hours of the previous
      * each hop amount ≥ layering_min_amount_retention × previous hop
      * first→last elapsed ≤ layering_max_elapsed_hours
    Sub-chains of a reported chain are suppressed. Missing timestamps fail the
    rule (no ordering is invented).
    """
    valid: list[tuple[dict, float]] = []
    for path in paths or []:
        node_ids = path.get("node_ids", [])
        transfers = path.get("transfers", [])
        hops = len(transfers)
        if hops < config.min_layering_hops or len(node_ids) != hops + 1:
            continue
        if len(set(node_ids)) != len(node_ids):
            continue  # revisits are cycles, handled by the cluster detector
        ok, elapsed_h = _valid_chain(transfers, config)
        if ok:
            valid.append((path, elapsed_h))

    # Longest first; drop chains whose transfers are a subset of a kept chain.
    valid.sort(key=lambda x: -len(x[0]["transfers"]))
    kept: list[tuple[dict, float]] = []
    kept_sets: list[set] = []
    for path, el in valid:
        ids = {t.get("tx_graph_id") for t in path["transfers"]}
        if any(ids <= k for k in kept_sets):
            continue
        kept.append((path, el))
        kept_sets.append(ids)
        if len(kept) >= config.layering_path_limit:
            break

    findings = []
    for path, elapsed_h in kept:
        node_ids, transfers_raw = path["node_ids"], path["transfers"]
        hops = len(transfers_raw)
        refs = [
            TransferRef(
                tx_graph_id=t.get("tx_graph_id"),
                from_account_id=node_ids[i],
                to_account_id=node_ids[i + 1],
                amount=t.get("amount"),
                amount_str=t.get("amount_str"),
                currency=t.get("currency"),
                timestamp_utc=t.get("timestamp_utc"),
                channel=t.get("channel"),
            )
            for i, t in enumerate(transfers_raw)
        ]
        retention = (transfers_raw[-1]["amount"] / transfers_raw[0]["amount"]) if transfers_raw[0].get("amount") else None
        score = min(0.5 + 0.1 * (hops - config.min_layering_hops + 1)
                    + (0.2 if elapsed_h < config.layering_max_elapsed_hours / 6 else 0.0), 1.0)
        inter = node_ids[1:-1]
        findings.append(NetworkFinding(
            pattern_type=NetworkPatternType.LAYERING,
            rule_id=f"AGENT3.LAYERING.{_RULE_VERSION}",
            subject_account_id=subject_id,
            related_account_ids=list(node_ids),
            supporting_transfers=refs,
            layering_paths=[LayeringPath(account_ids=node_ids, hop_count=hops,
                                         transfers=refs, elapsed_hours=round(elapsed_h, 3))],
            transfer_count=hops,
            hop_count=hops,
            total_amount=_total_amount(transfers_raw),
            currency=_dominant_currency(transfers_raw),
            elapsed_minutes=round(elapsed_h * 60, 2),
            heuristic_score=round(score, 3),
            explanation=(
                f"Funds moved {hops} time-ordered hops from {node_ids[0]} to {node_ids[-1]} "
                f"through {len(inter)} intermediar{'y' if len(inter) == 1 else 'ies'} "
                f"({', '.join(inter[:3])}{'...' if len(inter) > 3 else ''}) in {elapsed_h:.1f}h; "
                + (f"the final hop carried {retention:.0%} of the first. " if retention else "")
                + "Each hop followed the previous within "
                f"{config.layering_hop_max_gap_hours:g}h with ≥{config.layering_min_amount_retention:.0%} "
                "amount retention. Prototype heuristic indicator, not a fraud determination."
            ),
            detection_parameters={
                "min_layering_hops": config.min_layering_hops,
                "max_layering_hops": config.max_layering_hops,
                "layering_max_elapsed_hours": config.layering_max_elapsed_hours,
                "layering_hop_max_gap_hours": config.layering_hop_max_gap_hours,
                "layering_min_amount_retention": config.layering_min_amount_retention,
            },
        ))
    return findings


# ---------------------------------------------------------------------------
# Detector B: Structuring (just-below-round-amount transfers in a window)
# ---------------------------------------------------------------------------

def _near_below_round(amount: Optional[float], config: Agent3Config) -> bool:
    if amount is None or amount <= 0:
        return False
    unit = config.structuring_round_unit
    ceiling = math.ceil(amount / unit) * unit
    if ceiling == amount:
        return False  # exactly round is not "just below"
    return amount >= ceiling * (1 - config.structuring_proximity_pct)


def detect_structuring(
    outgoing: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect structuring-like splitting.

    Detection rule: AGENT3.STRUCTURING.v2
    ≥ structuring_min_transfers outgoing transfers within
    structuring_window_hours whose amounts each sit just below a multiple of
    structuring_round_unit (within structuring_proximity_pct).

    PROTOTYPE ENGINEERING HEURISTIC — the round unit is configurable and is
    NOT a regulatory reporting threshold.
    """
    candidates = [(r, t) for r, t in _ts_sorted(outgoing) if _near_below_round(r.get("amount"), config)]
    if len(candidates) < config.structuring_min_transfers:
        return []
    window = config.structuring_window_hours * 3600
    best: list[tuple[dict, datetime]] = []
    j = 0
    for i in range(len(candidates)):
        while candidates[i][1].timestamp() - candidates[j][1].timestamp() > window:
            j += 1
        if i - j + 1 > len(best):
            best = candidates[j: i + 1]
    if len(best) < config.structuring_min_transfers:
        return []
    rows = [r for r, _ in best]
    elapsed_h = (best[-1][1] - best[0][1]).total_seconds() / 3600
    recipients = {r.get("counterpart_id") for r in rows if r.get("counterpart_id")}
    return [NetworkFinding(
        pattern_type=NetworkPatternType.STRUCTURING,
        rule_id=f"AGENT3.STRUCTURING.{_RULE_VERSION}",
        subject_account_id=subject_id,
        related_account_ids=sorted(recipients),
        supporting_transfers=[_row_to_transfer_ref(r, from_id=subject_id, to_id=r.get("counterpart_id")) for r in rows],
        transfer_count=len(rows),
        distinct_counterparty_count=len(recipients),
        total_amount=_total_amount(rows),
        currency=_dominant_currency(rows),
        elapsed_minutes=round(elapsed_h * 60, 2),
        heuristic_score=round(min(len(rows) / (config.structuring_min_transfers * 2), 1.0), 3),
        explanation=(
            f"{subject_id} made {len(rows)} transfers to {len(recipients)} recipient(s) within "
            f"{elapsed_h:.1f}h, each just below a multiple of {config.structuring_round_unit:,.0f} "
            f"(within {config.structuring_proximity_pct:.0%}). Structuring-like splitting indicator "
            "(prototype heuristic; not a regulatory threshold)."
        ),
        detection_parameters={
            "structuring_min_transfers": config.structuring_min_transfers,
            "structuring_window_hours": config.structuring_window_hours,
            "structuring_round_unit": config.structuring_round_unit,
            "structuring_proximity_pct": config.structuring_proximity_pct,
        },
    )]


# ---------------------------------------------------------------------------
# Detectors C/D: Fan-in / Fan-out (distinct counterparties in a window)
# ---------------------------------------------------------------------------

def _fan(rows: list[dict], subject_id: str, config: Agent3Config, incoming: bool) -> list[NetworkFinding]:
    threshold = config.fan_in_min_sources if incoming else config.fan_out_min_destinations
    window = _best_window(_ts_sorted(rows), config.fan_window_hours * 3600, "counterpart_id")
    parties = {r.get("counterpart_id") for r, _ in window if r.get("counterpart_id")}
    if len(parties) < threshold:
        return []
    group = [r for r, _ in window]
    elapsed_h = (window[-1][1] - window[0][1]).total_seconds() / 3600
    kind = NetworkPatternType.FAN_IN if incoming else NetworkPatternType.FAN_OUT
    verb = "received transfers from" if incoming else "sent transfers to"
    noun = "sources" if incoming else "recipients"
    return [NetworkFinding(
        pattern_type=kind,
        rule_id=f"AGENT3.{kind.value}.{_RULE_VERSION}",
        subject_account_id=subject_id,
        related_account_ids=sorted(parties),
        supporting_transfers=[
            _row_to_transfer_ref(r, from_id=r.get("counterpart_id") if incoming else subject_id,
                                 to_id=subject_id if incoming else r.get("counterpart_id"))
            for r in group
        ],
        transfer_count=len(group),
        distinct_counterparty_count=len(parties),
        total_amount=_total_amount(group),
        currency=_dominant_currency(group),
        elapsed_minutes=round(elapsed_h * 60, 2),
        heuristic_score=round(min(len(parties) / (threshold * 2), 1.0), 3),
        explanation=(
            f"{subject_id} {verb} {len(parties)} distinct {noun} within {elapsed_h:.1f}h "
            f"(threshold: ≥{threshold} within {config.fan_window_hours:g}h). "
            f"{'Fan-in' if incoming else 'Fan-out'} indicator; not a fraud determination."
        ),
        detection_parameters={
            ("fan_in_min_sources" if incoming else "fan_out_min_destinations"): threshold,
            "fan_window_hours": config.fan_window_hours,
        },
    )]


def detect_fan_in(incoming: list[dict], subject_id: str, config: Agent3Config) -> list[NetworkFinding]:
    """Detection rule AGENT3.FAN_IN.v2: ≥ fan_in_min_sources distinct sources within fan_window_hours."""
    return _fan(incoming, subject_id, config, incoming=True)


def detect_fan_out(outgoing: list[dict], subject_id: str, config: Agent3Config) -> list[NetworkFinding]:
    """Detection rule AGENT3.FAN_OUT.v2: ≥ fan_out_min_destinations distinct recipients within fan_window_hours."""
    return _fan(outgoing, subject_id, config, incoming=False)


# ---------------------------------------------------------------------------
# Detector E: Mule-like pass-through
# ---------------------------------------------------------------------------

def detect_mule_like(
    incoming: list[dict],
    outgoing: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect mule-like pass-through behaviour.

    Detection rule: AGENT3.MULE_LIKE.v2
    Within some window of mule_window_hours starting at an incoming transfer:
      1. ≥ mule_min_incoming_sources distinct sources sent funds in;
      2. ≥ mule_min_outgoing_destinations destinations received funds out
         AFTER the first incoming transfer;
      3. total out ≥ mule_min_passthrough_ratio × total in.
    HEURISTIC INDICATOR of possible mule-like behaviour, not an identification.
    """
    ins, outs = _ts_sorted(incoming), _ts_sorted(outgoing)
    if not ins or not outs:
        return []
    window = timedelta(hours=config.mule_window_hours)
    for i, (_, start) in enumerate(ins):
        end = start + window
        w_in = [r for r, t in ins[i:] if t <= end]
        w_out = [r for r, t in outs if start < t <= end]
        sources = {r.get("counterpart_id") for r in w_in if r.get("counterpart_id")}
        dests = {r.get("counterpart_id") for r in w_out if r.get("counterpart_id")}
        total_in = _total_amount(w_in) or 0.0
        total_out = _total_amount(w_out) or 0.0
        if (len(sources) >= config.mule_min_incoming_sources
                and len(dests) >= config.mule_min_outgoing_destinations
                and total_in > 0
                and total_out >= config.mule_min_passthrough_ratio * total_in):
            ratio = total_out / total_in
            refs = ([_row_to_transfer_ref(r, from_id=r.get("counterpart_id"), to_id=subject_id) for r in w_in]
                    + [_row_to_transfer_ref(r, from_id=subject_id, to_id=r.get("counterpart_id")) for r in w_out])
            return [NetworkFinding(
                pattern_type=NetworkPatternType.MULE_LIKE,
                rule_id=f"AGENT3.MULE_LIKE.{_RULE_VERSION}",
                subject_account_id=subject_id,
                related_account_ids=sorted(sources | dests),
                supporting_transfers=refs,
                transfer_count=len(refs),
                distinct_counterparty_count=len(sources | dests),
                total_amount=total_in + total_out,
                currency=_dominant_currency(w_in + w_out),
                heuristic_score=round(min(0.5 + 0.1 * len(sources) + 0.2 * min(ratio, 1.0), 1.0), 3),
                explanation=(
                    f"{subject_id} received {total_in:,.2f} from {len(sources)} distinct source(s) and "
                    f"passed {ratio:.0%} of it ({total_out:,.2f}) to {len(dests)} destination(s) within "
                    f"{config.mule_window_hours:g}h. Heuristic indicator of POSSIBLE mule-like "
                    "pass-through; NOT a confirmed identification of a money mule."
                ),
                detection_parameters={
                    "mule_min_incoming_sources": config.mule_min_incoming_sources,
                    "mule_min_outgoing_destinations": config.mule_min_outgoing_destinations,
                    "mule_window_hours": config.mule_window_hours,
                    "mule_min_passthrough_ratio": config.mule_min_passthrough_ratio,
                },
            )]
    return []


# ---------------------------------------------------------------------------
# Detector F: Rapid forwarding
# ---------------------------------------------------------------------------

def detect_rapid_forwarding(
    incoming: list[dict],
    outgoing: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect rapid forwarding.

    Detection rule: AGENT3.RAPID_FORWARDING.v2
    An outgoing transfer within rapid_forwarding_window_minutes after an
    incoming transfer, carrying ≥ rapid_forwarding_min_ratio of its amount.
    All qualifying pairs for the subject are reported in ONE finding.
    """
    ins, outs = _ts_sorted(incoming), _ts_sorted(outgoing)
    pairs = []
    used_out: set = set()
    for in_row, in_ts in ins:
        for out_row, out_ts in outs:
            key = out_row.get("tx_graph_id")
            if key in used_out:
                continue
            mins = (out_ts - in_ts).total_seconds() / 60
            if mins <= 0 or mins > config.rapid_forwarding_window_minutes:
                continue
            in_amt, out_amt = in_row.get("amount"), out_row.get("amount")
            if not in_amt or out_amt is None or out_amt < config.rapid_forwarding_min_ratio * in_amt:
                continue
            pairs.append((in_row, out_row, mins))
            used_out.add(key)
            break
    if not pairs:
        return []
    refs, related = [], set()
    for in_row, out_row, _ in pairs:
        refs.append(_row_to_transfer_ref(in_row, from_id=in_row.get("counterpart_id"), to_id=subject_id))
        refs.append(_row_to_transfer_ref(out_row, from_id=subject_id, to_id=out_row.get("counterpart_id")))
        related.update(filter(None, [in_row.get("counterpart_id"), out_row.get("counterpart_id")]))
    fastest = min(m for *_, m in pairs)
    return [NetworkFinding(
        pattern_type=NetworkPatternType.RAPID_FORWARDING,
        rule_id=f"AGENT3.RAPID_FORWARDING.{_RULE_VERSION}",
        subject_account_id=subject_id,
        related_account_ids=sorted(related),
        supporting_transfers=refs,
        transfer_count=len(refs),
        elapsed_minutes=round(fastest, 2),
        total_amount=_total_amount([p[1] for p in pairs]),
        currency=_dominant_currency([p[1] for p in pairs]),
        heuristic_score=round(min(0.4 + 0.15 * len(pairs)
                                  + 0.3 * (1 - fastest / config.rapid_forwarding_window_minutes), 1.0), 3),
        explanation=(
            f"{subject_id} forwarded funds {len(pairs)} time(s) shortly after receiving them "
            f"(fastest {fastest:.1f} min; threshold ≤{config.rapid_forwarding_window_minutes:g} min and "
            f"≥{config.rapid_forwarding_min_ratio:.0%} of the incoming amount). Rapid-forwarding indicator."
        ),
        detection_parameters={
            "rapid_forwarding_window_minutes": config.rapid_forwarding_window_minutes,
            "rapid_forwarding_min_ratio": config.rapid_forwarding_min_ratio,
        },
    )]


# ---------------------------------------------------------------------------
# Detector G: Suspicious cluster (time-ordered cycle)
# ---------------------------------------------------------------------------

def detect_suspicious_cluster(
    cycles: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect suspicious clusters as time-ordered transfer cycles.

    Detection rule: AGENT3.SUSPICIOUS_CLUSTER.v2
    ``cycles`` are candidate closed walks ({node_ids, transfers}) starting and
    ending at the subject. A cycle is flagged when:
      * it has ≥ cluster_min_edges transfers and ≥ cluster_min_accounts
        distinct accounts (and ≤ cluster_max_cycle_length);
      * timestamps are present and some rotation of the cycle is strictly
        increasing (the funds went round once, starting at some member);
      * first→last elapsed ≤ cluster_window_hours.
    Distinct account sets are reported once (up to 3 findings).
    """
    findings, seen = [], set()
    for c in cycles or []:
        node_ids, transfers = c.get("node_ids", []), c.get("transfers", [])
        accounts = set(node_ids)
        if (len(transfers) < config.cluster_min_edges or len(accounts) < config.cluster_min_accounts
                or len(transfers) > config.cluster_max_cycle_length
                or not node_ids or node_ids[0] != node_ids[-1]):
            continue
        times = [_parse_ts(t.get("timestamp_utc")) for t in transfers]
        if any(t is None for t in times):
            continue
        # A closed cycle is time-ordered if SOME rotation is strictly
        # increasing, i.e. at most one "descent" going around the cycle.
        n = len(times)
        descents = [i for i in range(n) if times[(i + 1) % n] <= times[i]]
        if len(descents) != 1:
            continue
        start = (descents[0] + 1) % n
        transfers = transfers[start:] + transfers[:start]
        times = times[start:] + times[:start]
        node_ids = node_ids[start:-1] + node_ids[:start] + [node_ids[start]]
        elapsed_h = (times[-1] - times[0]).total_seconds() / 3600
        if elapsed_h > config.cluster_window_hours:
            continue
        key = frozenset(accounts)
        if key in seen:
            continue
        seen.add(key)
        refs = [
            TransferRef(tx_graph_id=t.get("tx_graph_id"), from_account_id=node_ids[i],
                        to_account_id=node_ids[i + 1], amount=t.get("amount"), amount_str=t.get("amount_str"),
                        currency=t.get("currency"), timestamp_utc=t.get("timestamp_utc"), channel=t.get("channel"))
            for i, t in enumerate(transfers)
        ]
        findings.append(NetworkFinding(
            pattern_type=NetworkPatternType.SUSPICIOUS_CLUSTER,
            rule_id=f"AGENT3.SUSPICIOUS_CLUSTER.{_RULE_VERSION}",
            subject_account_id=subject_id,
            related_account_ids=sorted(accounts - {subject_id}),
            supporting_transfers=refs,
            transfer_count=len(refs),
            distinct_counterparty_count=len(accounts),
            total_amount=_total_amount(transfers),
            currency=_dominant_currency(transfers),
            elapsed_minutes=round(elapsed_h * 60, 2),
            heuristic_score=round(min(0.6 + 0.05 * len(accounts)
                                      + (0.2 if elapsed_h < config.cluster_window_hours / 3 else 0.0), 1.0), 3),
            explanation=(
                f"Funds circulated through {subject_id} in a time-ordered cycle of "
                f"{len(accounts)} accounts ({' → '.join(node_ids)}) within {elapsed_h:.1f}h "
                f"(threshold ≤{config.cluster_window_hours:g}h). Circular-flow cluster indicator; "
                "not a fraud determination."
            ),
            detection_parameters={
                "cluster_min_accounts": config.cluster_min_accounts,
                "cluster_min_edges": config.cluster_min_edges,
                "cluster_max_cycle_length": config.cluster_max_cycle_length,
                "cluster_window_hours": config.cluster_window_hours,
            },
        ))
        if len(findings) >= 3:
            break
    return findings
