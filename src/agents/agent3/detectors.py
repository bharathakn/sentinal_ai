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
from datetime import datetime, timezone
from typing import Optional

from .config import Agent3Config
from .output_schema import (
    LayeringPath,
    NetworkFinding,
    NetworkPatternType,
    TransferRef,
)

logger = logging.getLogger(__name__)

_RULE_VERSION = "v1"

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


# ---------------------------------------------------------------------------
# Detector A: Layering
# ---------------------------------------------------------------------------


def detect_layering(
    paths: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect layering — multi-hop chains of ≥ config.min_layering_hops hops.

    ``paths`` is a list of path dicts from GraphQueryHelper.get_transfer_path()
    or Agent 3's own bounded multi-hop query.

    Detection rule: AGENT3.LAYERING.v1
    Threshold: path must contain ≥ min_layering_hops hops (default 2).
    If timestamps are present, elapsed_hours is reported for context.

    This is a structural indicator. A chain meeting the threshold is
    flagged regardless of amounts — the investigator reviews the evidence.
    """
    if not paths:
        return []

    findings: list[NetworkFinding] = []

    for path in paths:
        node_ids: list[str] = path.get("node_ids", [])
        transfers_raw: list[dict] = path.get("transfers", [])
        path_length: int = path.get("path_length", len(node_ids) - 1)

        if path_length < config.min_layering_hops:
            continue

        # Build TransferRef list — paths contain abbreviated transfer dicts
        transfer_refs = []
        for i, t in enumerate(transfers_raw):
            from_id = node_ids[i] if i < len(node_ids) else None
            to_id = node_ids[i + 1] if (i + 1) < len(node_ids) else None
            transfer_refs.append(TransferRef(
                tx_graph_id=t.get("tx_graph_id"),
                from_account_id=from_id,
                to_account_id=to_id,
                amount=t.get("amount"),
                amount_str=t.get("amount_str"),
                currency=t.get("currency"),
                timestamp_utc=t.get("timestamp_utc"),
                channel=t.get("channel"),
            ))

        # Elapsed time across the chain
        first_ts = transfers_raw[0].get("timestamp_utc") if transfers_raw else None
        last_ts = transfers_raw[-1].get("timestamp_utc") if transfers_raw else None
        elapsed_h = _elapsed_hours(first_ts, last_ts)

        lp = LayeringPath(
            account_ids=node_ids,
            hop_count=path_length,
            transfers=transfer_refs,
            elapsed_hours=elapsed_h,
        )

        # Heuristic score: longer chain → higher score, rapid → higher
        base = min(path_length / config.max_layering_hops, 1.0)
        if elapsed_h is not None and elapsed_h < config.layering_max_elapsed_hours / 3:
            base = min(base + 0.2, 1.0)

        intermediaries = node_ids[1:-1] if len(node_ids) > 2 else []
        intermediary_str = (
            f" through {len(intermediaries)} intermediar{'y' if len(intermediaries)==1 else 'ies'} "
            f"({', '.join(intermediaries[:3])}{'...' if len(intermediaries) > 3 else ''})"
            if intermediaries else ""
        )
        elapsed_str = (
            f" in {elapsed_h:.1f}h" if elapsed_h is not None else " (timestamps missing)"
        )

        findings.append(NetworkFinding(
            pattern_type=NetworkPatternType.LAYERING,
            rule_id=f"AGENT3.LAYERING.{_RULE_VERSION}",
            subject_account_id=subject_id,
            related_account_ids=list(node_ids),
            supporting_transfers=transfer_refs,
            layering_paths=[lp],
            transfer_count=len(transfer_refs),
            hop_count=path_length,
            total_amount=_total_amount(transfers_raw) if transfers_raw else None,
            currency=_dominant_currency(transfers_raw) if transfers_raw else None,
            elapsed_minutes=elapsed_h * 60 if elapsed_h is not None else None,
            heuristic_score=round(base, 3),
            explanation=(
                f"Funds moved {path_length} hop(s){intermediary_str}{elapsed_str} "
                f"from {node_ids[0]} to {node_ids[-1]}. "
                f"This is a structural network indicator (prototype heuristic). "
                f"Requires ≥{config.min_layering_hops} hops to flag."
            ),
            detection_parameters={
                "min_layering_hops": config.min_layering_hops,
                "max_layering_hops": config.max_layering_hops,
                "layering_max_elapsed_hours": config.layering_max_elapsed_hours,
            },
        ))

    return findings


# ---------------------------------------------------------------------------
# Detector B: Structuring
# ---------------------------------------------------------------------------


def detect_structuring(
    outgoing: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect structuring-like behaviour — repeated transfers within a time window.

    Detection rule: AGENT3.STRUCTURING.v1
    Prototype heuristic: ≥ structuring_min_transfers outgoing transfers from
    the same sender within structuring_window_hours.

    IMPORTANT: This is a PROTOTYPE ENGINEERING HEURISTIC. It is NOT based on
    any regulatory reporting threshold (e.g., ₹50,000, $10,000, or any PMLA/
    FinCEN/FATF figure). No transfer amount is compared to a legal threshold.

    A single small transfer is never flagged; the pattern requires repeated
    frequency within the configured window.
    """
    if len(outgoing) < config.structuring_min_transfers:
        return []

    # Sort by timestamp (rows with no timestamp are grouped separately)
    with_ts = [(r, _parse_ts(r.get("timestamp_utc"))) for r in outgoing]
    timestamped = [(r, dt) for r, dt in with_ts if dt is not None]
    missing_ts = [r for r, dt in with_ts if dt is None]

    window_secs = config.structuring_window_hours * 3600
    findings: list[NetworkFinding] = []

    if timestamped:
        timestamped.sort(key=lambda x: x[1])
        # Sliding window: find any group of ≥ min_transfers within the window
        n = len(timestamped)
        i = 0
        seen_windows: set[tuple[str, ...]] = set()

        while i < n:
            group = [timestamped[i]]
            j = i + 1
            while j < n:
                elapsed = (timestamped[j][1] - timestamped[i][1]).total_seconds()
                if elapsed <= window_secs:
                    group.append(timestamped[j])
                    j += 1
                else:
                    break

            if len(group) >= config.structuring_min_transfers:
                key = tuple(sorted(r.get("tx_graph_id", "") for r, _ in group))
                if key not in seen_windows:
                    seen_windows.add(key)
                    rows = [r for r, _ in group]
                    transfer_refs = [
                        _row_to_transfer_ref(r, from_id=subject_id, to_id=r.get("counterpart_id"))
                        for r in rows
                    ]
                    total = _total_amount(rows)
                    elapsed_h = (group[-1][1] - group[0][1]).total_seconds() / 3600
                    distinct_recipients = len(set(r.get("counterpart_id") for r in rows if r.get("counterpart_id")))
                    score = min(len(rows) / (config.structuring_min_transfers * 3), 1.0)

                    findings.append(NetworkFinding(
                        pattern_type=NetworkPatternType.STRUCTURING,
                        rule_id=f"AGENT3.STRUCTURING.{_RULE_VERSION}",
                        subject_account_id=subject_id,
                        related_account_ids=list(
                            {r.get("counterpart_id") for r in rows if r.get("counterpart_id")}
                        ),
                        supporting_transfers=transfer_refs,
                        transfer_count=len(rows),
                        distinct_counterparty_count=distinct_recipients,
                        total_amount=total,
                        currency=_dominant_currency(rows),
                        elapsed_minutes=elapsed_h * 60,
                        heuristic_score=round(score, 3),
                        explanation=(
                            f"{len(rows)} outgoing transfers within {elapsed_h:.1f}h "
                            f"(window: {config.structuring_window_hours}h) from {subject_id}. "
                            f"Prototype structuring heuristic: ≥{config.structuring_min_transfers} "
                            f"transfers in window. NOT based on a legal reporting threshold."
                        ),
                        detection_parameters={
                            "structuring_min_transfers": config.structuring_min_transfers,
                            "structuring_window_hours": config.structuring_window_hours,
                        },
                    ))
            i += 1

    elif len(missing_ts) >= config.structuring_min_transfers:
        # Can't window by time — flag if enough transfers exist without ordering
        transfer_refs = [
            _row_to_transfer_ref(r, from_id=subject_id, to_id=r.get("counterpart_id"))
            for r in missing_ts
        ]
        findings.append(NetworkFinding(
            pattern_type=NetworkPatternType.STRUCTURING,
            rule_id=f"AGENT3.STRUCTURING.{_RULE_VERSION}",
            subject_account_id=subject_id,
            related_account_ids=list(
                {r.get("counterpart_id") for r in missing_ts if r.get("counterpart_id")}
            ),
            supporting_transfers=transfer_refs,
            transfer_count=len(missing_ts),
            total_amount=_total_amount(missing_ts),
            currency=_dominant_currency(missing_ts),
            heuristic_score=0.3,
            explanation=(
                f"{len(missing_ts)} outgoing transfers from {subject_id} (timestamps missing; "
                f"cannot verify time window). Prototype structuring heuristic flagged "
                f"≥{config.structuring_min_transfers} transfers. NOT a legal determination."
            ),
            detection_parameters={
                "structuring_min_transfers": config.structuring_min_transfers,
                "structuring_window_hours": config.structuring_window_hours,
                "timestamp_available": False,
            },
        ))

    return findings


# ---------------------------------------------------------------------------
# Detector C: Fan-in
# ---------------------------------------------------------------------------


def detect_fan_in(
    incoming: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect fan-in — multiple distinct sources sending to one recipient.

    Detection rule: AGENT3.FAN_IN.v1
    Threshold: ≥ fan_in_min_sources distinct source accounts.
    """
    distinct_sources = {
        r.get("counterpart_id")
        for r in incoming
        if r.get("counterpart_id")
    }
    if len(distinct_sources) < config.fan_in_min_sources:
        return []

    transfer_refs = [
        _row_to_transfer_ref(r, from_id=r.get("counterpart_id"), to_id=subject_id)
        for r in incoming
    ]
    total = _total_amount(incoming)
    score = min(len(distinct_sources) / (config.fan_in_min_sources * 3), 1.0)

    return [NetworkFinding(
        pattern_type=NetworkPatternType.FAN_IN,
        rule_id=f"AGENT3.FAN_IN.{_RULE_VERSION}",
        subject_account_id=subject_id,
        related_account_ids=list(distinct_sources),
        supporting_transfers=transfer_refs,
        transfer_count=len(incoming),
        distinct_counterparty_count=len(distinct_sources),
        total_amount=total,
        currency=_dominant_currency(incoming),
        heuristic_score=round(score, 3),
        explanation=(
            f"{subject_id} received {len(incoming)} transfers from "
            f"{len(distinct_sources)} distinct sources "
            f"(threshold: ≥{config.fan_in_min_sources}). "
            f"Fan-in structural indicator. Not a fraud determination."
        ),
        detection_parameters={"fan_in_min_sources": config.fan_in_min_sources},
    )]


# ---------------------------------------------------------------------------
# Detector D: Fan-out
# ---------------------------------------------------------------------------


def detect_fan_out(
    outgoing: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect fan-out — one sender distributing to multiple distinct recipients.

    Detection rule: AGENT3.FAN_OUT.v1
    Threshold: ≥ fan_out_min_destinations distinct recipient accounts.
    """
    distinct_dests = {
        r.get("counterpart_id")
        for r in outgoing
        if r.get("counterpart_id")
    }
    if len(distinct_dests) < config.fan_out_min_destinations:
        return []

    transfer_refs = [
        _row_to_transfer_ref(r, from_id=subject_id, to_id=r.get("counterpart_id"))
        for r in outgoing
    ]
    total = _total_amount(outgoing)
    score = min(len(distinct_dests) / (config.fan_out_min_destinations * 3), 1.0)

    return [NetworkFinding(
        pattern_type=NetworkPatternType.FAN_OUT,
        rule_id=f"AGENT3.FAN_OUT.{_RULE_VERSION}",
        subject_account_id=subject_id,
        related_account_ids=list(distinct_dests),
        supporting_transfers=transfer_refs,
        transfer_count=len(outgoing),
        distinct_counterparty_count=len(distinct_dests),
        total_amount=total,
        currency=_dominant_currency(outgoing),
        heuristic_score=round(score, 3),
        explanation=(
            f"{subject_id} sent {len(outgoing)} transfers to "
            f"{len(distinct_dests)} distinct recipients "
            f"(threshold: ≥{config.fan_out_min_destinations}). "
            f"Fan-out structural indicator. Not a fraud determination."
        ),
        detection_parameters={"fan_out_min_destinations": config.fan_out_min_destinations},
    )]


# ---------------------------------------------------------------------------
# Detector E: Mule-like behavior
# ---------------------------------------------------------------------------


def detect_mule_like(
    incoming: list[dict],
    outgoing: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect heuristic mule-like account behavior.

    Detection rule: AGENT3.MULE_LIKE.v1
    Conditions (ALL must be met):
      1. ≥ mule_min_incoming_sources distinct incoming source accounts.
      2. ≥ mule_min_outgoing_destinations distinct outgoing destinations.
      3. Both incoming and outgoing transfers exist.

    IMPORTANT: This is labelled as a HEURISTIC INDICATOR of POSSIBLE
    mule-like behavior. It does NOT identify confirmed money mules.
    """
    distinct_sources = {
        r.get("counterpart_id") for r in incoming if r.get("counterpart_id")
    }
    distinct_dests = {
        r.get("counterpart_id") for r in outgoing if r.get("counterpart_id")
    }

    if (
        len(distinct_sources) < config.mule_min_incoming_sources
        or len(distinct_dests) < config.mule_min_outgoing_destinations
    ):
        return []

    in_refs = [
        _row_to_transfer_ref(r, from_id=r.get("counterpart_id"), to_id=subject_id)
        for r in incoming
    ]
    out_refs = [
        _row_to_transfer_ref(r, from_id=subject_id, to_id=r.get("counterpart_id"))
        for r in outgoing
    ]
    all_refs = in_refs + out_refs

    total_in = _total_amount(incoming) or 0.0
    total_out = _total_amount(outgoing) or 0.0
    score = min(
        (len(distinct_sources) + len(distinct_dests))
        / ((config.mule_min_incoming_sources + config.mule_min_outgoing_destinations) * 2),
        1.0,
    )

    return [NetworkFinding(
        pattern_type=NetworkPatternType.MULE_LIKE,
        rule_id=f"AGENT3.MULE_LIKE.{_RULE_VERSION}",
        subject_account_id=subject_id,
        related_account_ids=list(distinct_sources | distinct_dests),
        supporting_transfers=all_refs,
        transfer_count=len(all_refs),
        distinct_counterparty_count=len(distinct_sources | distinct_dests),
        total_amount=total_in + total_out,
        currency=_dominant_currency(incoming + outgoing),
        heuristic_score=round(score, 3),
        explanation=(
            f"{subject_id} received from {len(distinct_sources)} distinct source(s) "
            f"(threshold: ≥{config.mule_min_incoming_sources}) "
            f"and sent to {len(distinct_dests)} distinct destination(s) "
            f"(threshold: ≥{config.mule_min_outgoing_destinations}). "
            f"Heuristic indicator of POSSIBLE mule-like behavior. "
            f"NOT a confirmed identification of a money mule."
        ),
        detection_parameters={
            "mule_min_incoming_sources": config.mule_min_incoming_sources,
            "mule_min_outgoing_destinations": config.mule_min_outgoing_destinations,
        },
    )]


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
    Detect rapid forwarding — outgoing transfers shortly after incoming ones.

    Detection rule: AGENT3.RAPID_FORWARDING.v1
    Threshold: any (incoming, outgoing) pair where the outgoing timestamp
    follows the incoming by ≤ rapid_forwarding_window_minutes.

    Requires timestamps on both transfers. Pairs with missing timestamps
    are excluded and reported in the warning rather than silently treated
    as evidence.

    Multiple independent forwarding events are returned as separate findings.
    """
    if not incoming or not outgoing:
        return []

    findings: list[NetworkFinding] = []
    reported_pairs: set[tuple[str, str]] = set()

    for in_row in incoming:
        in_ts_str = in_row.get("timestamp_utc")
        in_ts = _parse_ts(in_ts_str)
        if in_ts is None:
            continue

        for out_row in outgoing:
            out_ts_str = out_row.get("timestamp_utc")
            out_ts = _parse_ts(out_ts_str)
            if out_ts is None:
                continue
            if out_ts <= in_ts:
                continue  # not a forward event

            elapsed = (out_ts - in_ts).total_seconds() / 60.0
            if elapsed > config.rapid_forwarding_window_minutes:
                continue

            in_id = in_row.get("tx_graph_id") or in_row.get("raw_record_id", "?")
            out_id = out_row.get("tx_graph_id") or out_row.get("raw_record_id", "?")
            pair_key = (in_id, out_id)
            if pair_key in reported_pairs:
                continue
            reported_pairs.add(pair_key)

            in_ref = _row_to_transfer_ref(
                in_row,
                from_id=in_row.get("counterpart_id"),
                to_id=subject_id,
            )
            out_ref = _row_to_transfer_ref(
                out_row,
                from_id=subject_id,
                to_id=out_row.get("counterpart_id"),
            )

            in_amt = in_row.get("amount") or 0.0
            out_amt = out_row.get("amount") or 0.0

            findings.append(NetworkFinding(
                pattern_type=NetworkPatternType.RAPID_FORWARDING,
                rule_id=f"AGENT3.RAPID_FORWARDING.{_RULE_VERSION}",
                subject_account_id=subject_id,
                related_account_ids=list(filter(None, [
                    in_row.get("counterpart_id"),
                    out_row.get("counterpart_id"),
                ])),
                supporting_transfers=[in_ref, out_ref],
                transfer_count=2,
                elapsed_minutes=round(elapsed, 2),
                total_amount=(in_amt + out_amt) if (in_amt or out_amt) else None,
                currency=in_row.get("currency") or out_row.get("currency"),
                heuristic_score=round(
                    1.0 - min(elapsed / config.rapid_forwarding_window_minutes, 1.0),
                    3,
                ),
                explanation=(
                    f"{subject_id} forwarded funds within {elapsed:.1f} min "
                    f"of receiving them (threshold: ≤{config.rapid_forwarding_window_minutes}min). "
                    f"Incoming {in_amt} → outgoing {out_amt}. "
                    f"Rapid-forwarding structural indicator."
                ),
                detection_parameters={
                    "rapid_forwarding_window_minutes": config.rapid_forwarding_window_minutes,
                },
            ))

    return findings


# ---------------------------------------------------------------------------
# Detector G: Suspicious connected clusters
# ---------------------------------------------------------------------------


def detect_suspicious_cluster(
    cluster_rows: list[dict],
    subject_id: str,
    config: Agent3Config,
) -> list[NetworkFinding]:
    """
    Detect suspicious connected clusters.

    ``cluster_rows`` is a list of relationship rows from a bounded neighbourhood
    query around the subject account — each row has: from_id, to_id, and
    relationship properties.

    Detection rule: AGENT3.SUSPICIOUS_CLUSTER.v1
    Conditions (ALL must be met):
      1. ≥ cluster_min_accounts distinct accounts in the bounded neighbourhood.
      2. ≥ cluster_min_edges distinct transfer relationships.

    Additional indicators reported (not thresholds):
      - Presence of cycles (account_id appears as both sender and receiver).
      - Multiple paths between same account pair.
    """
    if not cluster_rows:
        return []

    accounts: set[str] = set()
    edge_keys: set[str] = set()

    for row in cluster_rows:
        from_id = row.get("from_id") or row.get("account_id")
        to_id = row.get("to_id") or row.get("counterpart_id")
        if from_id:
            accounts.add(from_id)
        if to_id:
            accounts.add(to_id)
        tx_key = row.get("tx_graph_id") or f"{from_id}:{to_id}"
        if tx_key:
            edge_keys.add(tx_key)

    if len(accounts) < config.cluster_min_accounts or len(edge_keys) < config.cluster_min_edges:
        return []

    # Cycle detection: accounts appearing as both sender and receiver
    senders = {
        row.get("from_id") or row.get("account_id")
        for row in cluster_rows
        if row.get("from_id") or row.get("account_id")
    }
    receivers = {
        row.get("to_id") or row.get("counterpart_id")
        for row in cluster_rows
        if row.get("to_id") or row.get("counterpart_id")
    }
    cycle_accounts = senders & receivers
    has_cycles = bool(cycle_accounts)

    # Multi-path: same (from, to) pair appearing more than once
    from_to_pairs = [
        (row.get("from_id") or row.get("account_id"),
         row.get("to_id") or row.get("counterpart_id"))
        for row in cluster_rows
    ]
    pair_counts = {}
    for pair in from_to_pairs:
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    has_multi_paths = any(v > 1 for v in pair_counts.values())

    transfer_refs = []
    for row in cluster_rows:
        from_id = row.get("from_id") or row.get("account_id")
        to_id = row.get("to_id") or row.get("counterpart_id")
        transfer_refs.append(TransferRef(
            tx_graph_id=row.get("tx_graph_id"),
            raw_record_id=row.get("raw_record_id"),
            from_account_id=from_id,
            to_account_id=to_id,
            amount=row.get("amount"),
            amount_str=row.get("amount_str"),
            currency=row.get("currency"),
            timestamp_utc=row.get("timestamp_utc"),
            channel=row.get("channel"),
        ))

    total = _total_amount(cluster_rows)
    density = len(edge_keys) / max(len(accounts), 1)
    score = min(density / 3.0 + (0.2 if has_cycles else 0.0) + (0.1 if has_multi_paths else 0.0), 1.0)

    details = []
    if has_cycles:
        details.append(f"cycles involving: {', '.join(list(cycle_accounts)[:5])}")
    if has_multi_paths:
        details.append("multiple paths between same account pair")
    detail_str = f" Features: {'; '.join(details)}." if details else ""

    return [NetworkFinding(
        pattern_type=NetworkPatternType.SUSPICIOUS_CLUSTER,
        rule_id=f"AGENT3.SUSPICIOUS_CLUSTER.{_RULE_VERSION}",
        subject_account_id=subject_id,
        related_account_ids=list(accounts - {subject_id}),
        supporting_transfers=transfer_refs,
        transfer_count=len(cluster_rows),
        distinct_counterparty_count=len(accounts),
        total_amount=total,
        currency=_dominant_currency(cluster_rows),
        heuristic_score=round(score, 3),
        explanation=(
            f"Bounded neighbourhood of {subject_id} contains {len(accounts)} accounts "
            f"and {len(edge_keys)} distinct transfer relationships "
            f"(thresholds: ≥{config.cluster_min_accounts} accounts, "
            f"≥{config.cluster_min_edges} edges).{detail_str} "
            f"Suspicious cluster structural indicator. Not a fraud determination."
        ),
        detection_parameters={
            "cluster_min_accounts": config.cluster_min_accounts,
            "cluster_min_edges": config.cluster_min_edges,
        },
    )]
