"""
Sentinel AI — Agent 3: Unit Tests (mocked graph queries)

All 10 required synthetic scenarios are covered:
  1.  Normal — no patterns detected
  2.  Mule-like network
  3.  Layering network
  4.  Fan-in network
  5.  Fan-out network
  6.  Rapid-forwarding network
  7.  Structuring-like network
  8.  Suspicious cluster
  9.  Mixed — multiple patterns overlap
  10. Insufficient evidence (missing timestamps / empty graph)

Plus:
  - Boundary conditions for each threshold
  - Missing timestamps handled safely
  - Multiple transactions between same account pair
  - Duplicate/overlapping finding suppression
  - Invalid inputs
  - Stable Pydantic mapping
  - Agent error handling (graph failures, missing config)
  - Pipeline state integration (LangGraph-compatible __call__)
  - VALIDATION_ERROR for missing account IDs
  - UNAVAILABLE when account not in graph
  - Empty findings list semantics
  - Output field presence and types

All tests use mocked Neo4j. No live database is required.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.agents.agent3.config import Agent3Config
from src.agents.agent3.output_schema import (
    Agent3Output,
    Agent3Status,
    NetworkPatternType,
    NetworkFinding,
)
from src.agents.agent3.detectors import (
    detect_fan_in,
    detect_fan_out,
    detect_layering,
    detect_mule_like,
    detect_rapid_forwarding,
    detect_structuring,
    detect_suspicious_cluster,
)
from src.agents.agent3.network_analyser import NetworkAnalyserAgent
from src.schemas.canonical_transaction import (
    AccountInfo,
    CanonicalTransaction,
    DataSource,
    TransactionChannel,
    TransactionStatus,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_CFG = Agent3Config(
    max_layering_hops=4,
    min_layering_hops=2,
    fan_in_min_sources=3,
    fan_out_min_destinations=3,
    structuring_min_transfers=3,
    structuring_window_hours=24.0,
    rapid_forwarding_window_minutes=120.0,
    mule_min_incoming_sources=2,
    mule_min_outgoing_destinations=2,
    cluster_min_accounts=4,
    cluster_min_edges=4,
    transfer_query_limit=100,
    layering_path_limit=5,
)

_T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _ts(delta_minutes: float = 0) -> str:
    return (_T0 + timedelta(minutes=delta_minutes)).isoformat()


def _make_tx(
    raw_id: str = "TXN001",
    sender_id: str = "ACC_A",
    receiver_id: str = "ACC_B",
    amount: str = "500.00",
) -> CanonicalTransaction:
    return CanonicalTransaction(
        raw_record_id=raw_id,
        source_dataset=DataSource.INDIA_SYNTHETIC,
        amount=Decimal(amount),
        currency="INR",
        timestamp=_T0,
        channel=TransactionChannel.UPI,
        status=TransactionStatus.SUCCESS,
        sender=AccountInfo(account_id=sender_id),
        receiver=AccountInfo(account_id=receiver_id),
    )


def _out_row(
    counterpart_id: str,
    amount: float = 100.0,
    ts_offset_min: float = 0,
    tx_id: str = "TXID",
) -> dict:
    return {
        "account_id": "ACC_A",
        "counterpart_id": counterpart_id,
        "tx_graph_id": f"{tx_id}::INDIA_SYNTHETIC",
        "raw_record_id": tx_id,
        "amount": amount,
        "amount_str": str(amount),
        "currency": "INR",
        "timestamp_utc": _ts(ts_offset_min),
        "channel": "UPI",
        "status": "SUCCESS",
    }


def _in_row(
    counterpart_id: str,
    amount: float = 100.0,
    ts_offset_min: float = 0,
    tx_id: str = "TXID",
) -> dict:
    return {
        "account_id": "ACC_A",
        "counterpart_id": counterpart_id,
        "tx_graph_id": f"{tx_id}::INDIA_SYNTHETIC",
        "raw_record_id": tx_id,
        "amount": amount,
        "amount_str": str(amount),
        "currency": "INR",
        "timestamp_utc": _ts(ts_offset_min),
        "channel": "UPI",
        "status": "SUCCESS",
    }


def _path_row(
    node_ids: list[str],
    path_length: int,
    amounts: list[float] = None,
) -> dict:
    transfers = []
    for i, nid in enumerate(node_ids[:-1]):
        transfers.append({
            "tx_graph_id": f"TX_{i}::DS",
            "amount": (amounts[i] if amounts else 100.0),
            "amount_str": str(amounts[i] if amounts else 100.0),
            "currency": "INR",
            "timestamp_utc": _ts(i * 10),
            "channel": "UPI",
        })
    return {
        "node_ids": node_ids,
        "transfers": transfers,
        "path_length": path_length,
    }


def _cluster_row(from_id: str, to_id: str, tx_id: str) -> dict:
    return {
        "from_id": from_id,
        "to_id": to_id,
        "tx_graph_id": f"{tx_id}::DS",
        "raw_record_id": tx_id,
        "amount": 100.0,
        "amount_str": "100.0",
        "currency": "INR",
        "timestamp_utc": _ts(0),
        "channel": "UPI",
    }


# ---------------------------------------------------------------------------
# 1. Normal — no patterns detected
# ---------------------------------------------------------------------------

class TestNormalNetwork:
    """Scenario 1: ordinary transfers, no threshold met."""

    def test_fan_in_below_threshold(self):
        # 2 sources, threshold is 3
        incoming = [
            _in_row("SRC1", tx_id="T1"),
            _in_row("SRC2", tx_id="T2"),
        ]
        result = detect_fan_in(incoming, "ACC_A", _CFG)
        assert result == []

    def test_fan_out_below_threshold(self):
        outgoing = [
            _out_row("DST1", tx_id="T1"),
            _out_row("DST2", tx_id="T2"),
        ]
        result = detect_fan_out(outgoing, "ACC_A", _CFG)
        assert result == []

    def test_structuring_below_threshold(self):
        outgoing = [_out_row("B", tx_id=f"T{i}", ts_offset_min=i * 60) for i in range(2)]
        result = detect_structuring(outgoing, "ACC_A", _CFG)
        assert result == []

    def test_layering_single_hop_not_flagged(self):
        """A 1-hop direct transfer is not layering."""
        paths = [_path_row(["A", "B"], path_length=1)]
        result = detect_layering(paths, "A", _CFG)
        assert result == []

    def test_rapid_forwarding_outside_window(self):
        """Forwarding after 3 hours — above default 2-hour window."""
        inc = [_in_row("SRC1", ts_offset_min=0, tx_id="IN1")]
        out = [_out_row("DST1", ts_offset_min=180, tx_id="OUT1")]  # 180 min > 120
        result = detect_rapid_forwarding(inc, out, "ACC_A", _CFG)
        assert result == []

    def test_mule_below_both_thresholds(self):
        inc = [_in_row("SRC1", tx_id="T1")]  # 1 source, need 2
        out = [_out_row("DST1", tx_id="T2")]  # 1 dest, need 2
        result = detect_mule_like(inc, out, "ACC_A", _CFG)
        assert result == []

    def test_cluster_below_threshold(self):
        rows = [
            _cluster_row("A", "B", "T1"),
            _cluster_row("A", "C", "T2"),
            _cluster_row("B", "C", "T3"),
        ]
        result = detect_suspicious_cluster(rows, "A", _CFG)
        # 3 accounts, 3 edges — below min of 4 each
        assert result == []


# ---------------------------------------------------------------------------
# 2. Mule-like network
# ---------------------------------------------------------------------------

class TestMuleLikeNetwork:
    """Scenario 2: receives from 2+ sources, sends to 2+ destinations."""

    def test_mule_detected(self):
        inc = [
            _in_row("SRC1", amount=500, ts_offset_min=0, tx_id="IN1"),
            _in_row("SRC2", amount=300, ts_offset_min=20, tx_id="IN2"),
        ]
        out = [
            _out_row("DST1", amount=400, ts_offset_min=60, tx_id="OUT1"),
            _out_row("DST2", amount=200, ts_offset_min=90, tx_id="OUT2"),
        ]  # 600 / 800 = 75% passed through
        result = detect_mule_like(inc, out, "ACC_A", _CFG)
        assert len(result) == 1
        f = result[0]
        assert f.pattern_type == NetworkPatternType.MULE_LIKE
        assert "MULE_LIKE" in f.rule_id
        assert "ACC_A" == f.subject_account_id
        assert len(f.supporting_transfers) == 4

    def test_mule_explanation_labels_heuristic(self):
        inc = [_in_row(f"SRC{i}", ts_offset_min=i * 10, tx_id=f"IN{i}") for i in range(2)]
        out = [_out_row(f"DST{i}", ts_offset_min=60 + i * 10, tx_id=f"OUT{i}") for i in range(2)]
        result = detect_mule_like(inc, out, "ACC_A", _CFG)
        assert "heuristic" in result[0].explanation.lower()
        assert "possible" in result[0].explanation.lower()

    def test_mule_one_source_not_flagged(self):
        inc = [_in_row("SRC1", tx_id="IN1")]  # only 1 source
        out = [_out_row(f"DST{i}", tx_id=f"OUT{i}") for i in range(3)]
        result = detect_mule_like(inc, out, "ACC_A", _CFG)
        assert result == []

    def test_mule_heuristic_score_in_range(self):
        inc = [_in_row(f"SRC{i}", ts_offset_min=i * 10, tx_id=f"IN{i}") for i in range(3)]
        out = [_out_row(f"DST{i}", ts_offset_min=60 + i * 10, tx_id=f"OUT{i}") for i in range(3)]
        result = detect_mule_like(inc, out, "ACC_A", _CFG)
        assert 0.0 <= result[0].heuristic_score <= 1.0

    def test_mule_low_passthrough_not_flagged(self):
        """v2: receiving from many and paying out a small fraction is not pass-through."""
        inc = [_in_row(f"SRC{i}", amount=1000, ts_offset_min=i * 10, tx_id=f"IN{i}") for i in range(3)]
        out = [_out_row("DST1", amount=500, ts_offset_min=60, tx_id="OUT1")]  # 500/3000
        assert detect_mule_like(inc, out, "ACC_A", _CFG) == []

    def test_mule_outgoing_before_incoming_not_flagged(self):
        """v2: money out BEFORE money in is not pass-through."""
        inc = [_in_row(f"SRC{i}", amount=100, ts_offset_min=100 + i, tx_id=f"IN{i}") for i in range(2)]
        out = [_out_row("DST1", amount=200, ts_offset_min=0, tx_id="OUT1")]
        assert detect_mule_like(inc, out, "ACC_A", _CFG) == []

    def test_mule_empty_outgoing(self):
        inc = [_in_row(f"SRC{i}", tx_id=f"IN{i}") for i in range(3)]
        result = detect_mule_like(inc, [], "ACC_A", _CFG)
        assert result == []


# ---------------------------------------------------------------------------
# 3. Layering network
# ---------------------------------------------------------------------------

class TestLayeringNetwork:
    """Scenario 3: multi-hop chain ≥2 hops."""

    def test_two_hop_layering_detected(self):
        paths = [_path_row(["A", "B", "C"], path_length=2)]
        result = detect_layering(paths, "A", _CFG)
        assert len(result) == 1
        f = result[0]
        assert f.pattern_type == NetworkPatternType.LAYERING
        assert f.hop_count == 2
        assert "A" in f.related_account_ids
        assert "B" in f.related_account_ids
        assert "C" in f.related_account_ids

    def test_three_hop_layering_detected(self):
        paths = [_path_row(["A", "B", "C", "D"], path_length=3)]
        result = detect_layering(paths, "A", _CFG)
        assert len(result) == 1
        assert result[0].hop_count == 3

    def test_layering_score_increases_with_hops(self):
        paths_2 = [_path_row(["A", "B", "C"], path_length=2)]
        paths_4 = [_path_row(["A", "B", "C", "D", "E"], path_length=4)]
        s2 = detect_layering(paths_2, "A", _CFG)[0].heuristic_score
        s4 = detect_layering(paths_4, "A", _CFG)[0].heuristic_score
        assert s4 >= s2

    def test_layering_paths_populated(self):
        paths = [_path_row(["A", "B", "C"], path_length=2)]
        result = detect_layering(paths, "A", _CFG)
        assert result[0].layering_paths[0].hop_count == 2

    def test_layering_missing_timestamps_not_flagged(self):
        """v2: time order cannot be established without timestamps — not flagged."""
        path = {
            "node_ids": ["A", "B", "C"],
            "transfers": [
                {"tx_graph_id": "T1::DS", "amount": 100.0, "amount_str": "100", "currency": "INR",
                 "timestamp_utc": None, "channel": "UPI"},
                {"tx_graph_id": "T2::DS", "amount": 90.0, "amount_str": "90", "currency": "INR",
                 "timestamp_utc": None, "channel": "UPI"},
            ],
            "path_length": 2,
        }
        result = detect_layering([path], "A", _CFG)
        assert result == []

    def test_layering_out_of_order_not_flagged(self):
        path = _path_row(["A", "B", "C"], 2)
        path["transfers"][1]["timestamp_utc"] = _ts(-30)  # second hop before first
        assert detect_layering([path], "A", _CFG) == []

    def test_layering_amount_drop_not_flagged(self):
        """v2: a hop carrying < retention × previous amount breaks the chain."""
        path = _path_row(["A", "B", "C"], 2, amounts=[1000.0, 300.0])
        assert detect_layering([path], "A", _CFG) == []

    def test_layering_slow_hop_not_flagged(self):
        path = _path_row(["A", "B", "C"], 2)
        path["transfers"][1]["timestamp_utc"] = _ts(7 * 60)  # 7h > 6h hop gap
        assert detect_layering([path], "A", _CFG) == []

    def test_layering_subchain_suppressed(self):
        long = _path_row(["A", "B", "C", "D"], 3)
        short = {"node_ids": ["A", "B", "C"], "transfers": long["transfers"][:2], "path_length": 2}
        result = detect_layering([short, long], "A", _CFG)
        assert len(result) == 1 and result[0].hop_count == 3

    def test_layering_repeated_account_not_flagged(self):
        path = _path_row(["A", "B", "A"], 2)
        assert detect_layering([path], "A", _CFG) == []


# ---------------------------------------------------------------------------
# 4. Fan-in network
# ---------------------------------------------------------------------------

class TestFanInNetwork:
    """Scenario 4: multiple sources to one recipient."""

    def test_fan_in_detected(self):
        incoming = [
            _in_row("SRC1", amount=200, tx_id="T1"),
            _in_row("SRC2", amount=300, tx_id="T2"),
            _in_row("SRC3", amount=150, tx_id="T3"),
        ]
        result = detect_fan_in(incoming, "RECV", _CFG)
        assert len(result) == 1
        f = result[0]
        assert f.pattern_type == NetworkPatternType.FAN_IN
        assert f.distinct_counterparty_count == 3
        assert f.transfer_count == 3

    def test_fan_in_total_amount(self):
        incoming = [
            _in_row("SRC1", amount=200, tx_id="T1"),
            _in_row("SRC2", amount=300, tx_id="T2"),
            _in_row("SRC3", amount=100, tx_id="T3"),
        ]
        result = detect_fan_in(incoming, "RECV", _CFG)
        assert abs(result[0].total_amount - 600.0) < 0.01

    def test_fan_in_threshold_boundary(self):
        """Exactly at threshold: 3 sources → detected."""
        incoming = [_in_row(f"SRC{i}", tx_id=f"T{i}") for i in range(3)]
        result = detect_fan_in(incoming, "RECV", _CFG)
        assert len(result) == 1

    def test_fan_in_one_below_threshold(self):
        """One below threshold: 2 sources → not detected."""
        incoming = [_in_row(f"SRC{i}", tx_id=f"T{i}") for i in range(2)]
        result = detect_fan_in(incoming, "RECV", _CFG)
        assert result == []

    def test_fan_in_score_in_range(self):
        incoming = [_in_row(f"SRC{i}", tx_id=f"T{i}") for i in range(5)]
        result = detect_fan_in(incoming, "RECV", _CFG)
        assert 0.0 <= result[0].heuristic_score <= 1.0


# ---------------------------------------------------------------------------
# 5. Fan-out network
# ---------------------------------------------------------------------------

class TestFanOutNetwork:
    """Scenario 5: one sender to many recipients."""

    def test_fan_out_detected(self):
        outgoing = [
            _out_row("DST1", amount=100, tx_id="T1"),
            _out_row("DST2", amount=120, tx_id="T2"),
            _out_row("DST3", amount=80, tx_id="T3"),
        ]
        result = detect_fan_out(outgoing, "SENDER", _CFG)
        assert len(result) == 1
        f = result[0]
        assert f.pattern_type == NetworkPatternType.FAN_OUT
        assert f.distinct_counterparty_count == 3

    def test_fan_out_threshold_boundary(self):
        outgoing = [_out_row(f"DST{i}", tx_id=f"T{i}") for i in range(3)]
        result = detect_fan_out(outgoing, "SENDER", _CFG)
        assert len(result) == 1

    def test_fan_out_below_threshold(self):
        outgoing = [_out_row(f"DST{i}", tx_id=f"T{i}") for i in range(2)]
        result = detect_fan_out(outgoing, "SENDER", _CFG)
        assert result == []

    def test_fan_out_same_destination_not_double_counted(self):
        """Multiple transfers to same destination count as 1 distinct dest."""
        outgoing = [
            _out_row("DST1", tx_id="T1"),
            _out_row("DST1", tx_id="T2"),  # same dest
            _out_row("DST2", tx_id="T3"),
        ]
        result = detect_fan_out(outgoing, "SENDER", _CFG)
        # only 2 distinct destinations — below threshold of 3
        assert result == []


# ---------------------------------------------------------------------------
# 6. Rapid-forwarding network
# ---------------------------------------------------------------------------

class TestRapidForwardingNetwork:
    """Scenario 6: incoming then outgoing within window."""

    def test_rapid_forwarding_detected(self):
        inc = [_in_row("SRC1", amount=500, ts_offset_min=0, tx_id="IN1")]
        out = [_out_row("DST1", amount=480, ts_offset_min=30, tx_id="OUT1")]
        result = detect_rapid_forwarding(inc, out, "ACC_A", _CFG)
        assert len(result) == 1
        f = result[0]
        assert f.pattern_type == NetworkPatternType.RAPID_FORWARDING
        assert abs(f.elapsed_minutes - 30.0) < 0.1

    def test_rapid_forwarding_score_higher_for_shorter_elapsed(self):
        inc = [_in_row("SRC1", ts_offset_min=0, tx_id="IN1")]
        out_fast = [_out_row("DST1", ts_offset_min=5, tx_id="FAST")]
        out_slow = [_out_row("DST1", ts_offset_min=100, tx_id="SLOW")]
        fast_score = detect_rapid_forwarding(inc, out_fast, "A", _CFG)[0].heuristic_score
        slow_score = detect_rapid_forwarding(inc, out_slow, "A", _CFG)[0].heuristic_score
        assert fast_score > slow_score

    def test_rapid_forwarding_outgoing_before_incoming_excluded(self):
        """Outgoing before incoming must not be flagged."""
        inc = [_in_row("SRC1", ts_offset_min=60, tx_id="IN1")]  # at t+60
        out = [_out_row("DST1", ts_offset_min=0, tx_id="OUT1")]  # at t0 (before)
        result = detect_rapid_forwarding(inc, out, "ACC_A", _CFG)
        assert result == []

    def test_rapid_forwarding_missing_timestamps_excluded(self):
        """Pairs with any missing timestamp must not produce a finding."""
        inc_no_ts = [{
            "account_id": "ACC_A", "counterpart_id": "SRC1",
            "tx_graph_id": "IN1::DS", "raw_record_id": "IN1",
            "amount": 500.0, "amount_str": "500", "currency": "INR",
            "timestamp_utc": None, "channel": "UPI",
        }]
        out = [_out_row("DST1", ts_offset_min=10, tx_id="OUT1")]
        result = detect_rapid_forwarding(inc_no_ts, out, "ACC_A", _CFG)
        assert result == []

    def test_rapid_forwarding_multiple_pairs(self):
        inc = [
            _in_row("SRC1", ts_offset_min=0, tx_id="IN1"),
            _in_row("SRC2", ts_offset_min=5, tx_id="IN2"),
        ]
        out = [
            _out_row("DST1", ts_offset_min=20, tx_id="OUT1"),
            _out_row("DST2", ts_offset_min=40, tx_id="OUT2"),
        ]
        result = detect_rapid_forwarding(inc, out, "ACC_A", _CFG)
        # Multiple pairs may be detected — none should be duplicated
        tx_pairs = [(f.supporting_transfers[0].tx_graph_id, f.supporting_transfers[1].tx_graph_id)
                    for f in result]
        assert len(tx_pairs) == len(set(tx_pairs))


# ---------------------------------------------------------------------------
# 7. Structuring-like network
# ---------------------------------------------------------------------------

class TestStructuringNetwork:
    """Scenario 7: repeated transfers within time window."""

    def test_structuring_detected_in_window(self):
        outgoing = [
            _out_row("B", amount=49500, ts_offset_min=0, tx_id="T1"),
            _out_row("C", amount=49800, ts_offset_min=60, tx_id="T2"),
            _out_row("D", amount=99000, ts_offset_min=120, tx_id="T3"),
        ]
        result = detect_structuring(outgoing, "A", _CFG)
        assert len(result) >= 1
        assert result[0].pattern_type == NetworkPatternType.STRUCTURING

    def test_structuring_ordinary_amounts_not_flagged(self):
        """v2: frequent payments of ordinary amounts are not structuring."""
        outgoing = [_out_row("B", amount=900 + i, ts_offset_min=i * 30, tx_id=f"T{i}") for i in range(5)]
        assert detect_structuring(outgoing, "A", _CFG) == []

    def test_structuring_exact_round_amount_not_flagged(self):
        outgoing = [_out_row("B", amount=50000, ts_offset_min=i * 30, tx_id=f"T{i}") for i in range(3)]
        assert detect_structuring(outgoing, "A", _CFG) == []

    def test_structuring_explanation_not_legal_threshold(self):
        outgoing = [_out_row("B", amount=49900, ts_offset_min=i * 30, tx_id=f"T{i}") for i in range(3)]
        result = detect_structuring(outgoing, "A", _CFG)
        assert result  # at least one finding
        explanation = result[0].explanation.lower()
        # Must not claim to be a legal/regulatory threshold
        assert "not based on a legal" in explanation or "prototype" in explanation

    def test_structuring_no_finding_outside_window(self):
        """Transfers spread > 24h apart — should not window together."""
        outgoing = [
            _out_row("B", amount=49500, ts_offset_min=0, tx_id="T1"),
            _out_row("C", amount=49500, ts_offset_min=25 * 60, tx_id="T2"),  # 25h later
            _out_row("D", amount=49500, ts_offset_min=50 * 60, tx_id="T3"),  # 50h later
        ]
        result = detect_structuring(outgoing, "A", _CFG)
        assert result == []

    def test_structuring_missing_timestamps_not_flagged(self):
        """v2: the window cannot be established without timestamps — not flagged."""
        rows = []
        for i in range(3):
            r = _out_row("B", amount=49500, tx_id=f"T{i}")
            r["timestamp_utc"] = None
            rows.append(r)
        assert detect_structuring(rows, "A", _CFG) == []


# ---------------------------------------------------------------------------
# 8. Suspicious cluster
# ---------------------------------------------------------------------------

class TestSuspiciousCluster:
    """Scenario 8: time-ordered transfer cycle (v2)."""

    @staticmethod
    def _cycle(nodes, minutes):
        return {
            "node_ids": nodes,
            "transfers": [
                {"tx_graph_id": f"C{i}::DS", "amount": 100.0, "amount_str": "100", "currency": "INR",
                 "timestamp_utc": _ts(m), "channel": "UPI"}
                for i, m in enumerate(minutes)
            ],
        }

    def test_cluster_detected(self):
        cyc = self._cycle(["A", "B", "C", "D", "A"], [0, 30, 60, 90])
        result = detect_suspicious_cluster([cyc], "A", _CFG)
        assert len(result) == 1
        assert result[0].pattern_type == NetworkPatternType.SUSPICIOUS_CLUSTER
        assert set(result[0].related_account_ids) == {"B", "C", "D"}

    def test_cluster_cycle_detected_in_explanation(self):
        cyc = self._cycle(["A", "B", "C", "D", "A"], [0, 30, 60, 90])
        result = detect_suspicious_cluster([cyc], "A", _CFG)
        assert "cycle" in result[0].explanation.lower()
        assert 0.0 < result[0].heuristic_score <= 1.0

    def test_cluster_rotation_detected(self):
        """Read from C, the ring C→D→A→B→C is ordered only from A — still a cycle."""
        cyc = self._cycle(["C", "D", "A", "B", "C"], [60, 90, 0, 30])
        result = detect_suspicious_cluster([cyc], "C", _CFG)
        assert len(result) == 1
        assert result[0].supporting_transfers[0].from_account_id == "A"

    def test_cluster_not_time_ordered_not_flagged(self):
        cyc = self._cycle(["A", "B", "C", "D", "A"], [0, 60, 30, 90])  # two descents
        assert detect_suspicious_cluster([cyc], "A", _CFG) == []

    def test_cluster_too_slow_not_flagged(self):
        cyc = self._cycle(["A", "B", "C", "D", "A"], [0, 30 * 60, 60 * 60, 80 * 60])  # 80h
        assert detect_suspicious_cluster([cyc], "A", _CFG) == []

    def test_cluster_below_threshold(self):
        cyc = self._cycle(["A", "B", "C", "A"], [0, 30, 60])  # 3 accounts < 4 in _CFG
        assert detect_suspicious_cluster([cyc], "A", _CFG) == []

    def test_cluster_duplicate_account_set_reported_once(self):
        c1 = self._cycle(["A", "B", "C", "D", "A"], [0, 30, 60, 90])
        c2 = self._cycle(["A", "B", "C", "D", "A"], [0, 31, 61, 91])
        assert len(detect_suspicious_cluster([c1, c2], "A", _CFG)) == 1

    def test_cluster_empty_rows(self):
        result = detect_suspicious_cluster([], "A", _CFG)
        assert result == []


# ---------------------------------------------------------------------------
# 9. Mixed — multiple patterns overlap
# ---------------------------------------------------------------------------

class TestMixedNetwork:
    """Scenario 9: multiple patterns detected in one analysis."""

    def test_mixed_fan_in_and_rapid_forwarding(self):
        # Fan-in: 3 sources
        inc = [
            _in_row("SRC1", amount=300, ts_offset_min=0, tx_id="IN1"),
            _in_row("SRC2", amount=400, ts_offset_min=5, tx_id="IN2"),
            _in_row("SRC3", amount=200, ts_offset_min=10, tx_id="IN3"),
        ]
        # Fan-out: 3 destinations
        out = [
            _out_row("DST1", amount=250, ts_offset_min=30, tx_id="OUT1"),
            _out_row("DST2", amount=300, ts_offset_min=45, tx_id="OUT2"),
            _out_row("DST3", amount=200, ts_offset_min=60, tx_id="OUT3"),
        ]
        fi = detect_fan_in(inc, "CENTER", _CFG)
        fo = detect_fan_out(out, "CENTER", _CFG)
        ml = detect_mule_like(inc, out, "CENTER", _CFG)
        rf = detect_rapid_forwarding(inc, out, "CENTER", _CFG)

        assert len(fi) == 1
        assert len(fo) == 1
        assert len(ml) == 1
        assert len(rf) >= 1  # at least one rapid-forwarding pair

        pattern_types = {f.pattern_type for findings in [fi, fo, ml, rf] for f in findings}
        assert NetworkPatternType.FAN_IN in pattern_types
        assert NetworkPatternType.FAN_OUT in pattern_types
        assert NetworkPatternType.MULE_LIKE in pattern_types
        assert NetworkPatternType.RAPID_FORWARDING in pattern_types

    def test_mixed_finding_ids_unique(self):
        """All findings in a mixed scenario must have unique finding_ids."""
        inc = [_in_row(f"SRC{i}", tx_id=f"IN{i}") for i in range(3)]
        out = [_out_row(f"DST{i}", ts_offset_min=30 + i * 10, tx_id=f"OUT{i}") for i in range(3)]
        all_findings = (
            detect_fan_in(inc, "C", _CFG)
            + detect_fan_out(out, "C", _CFG)
            + detect_mule_like(inc, out, "C", _CFG)
            + detect_rapid_forwarding(inc, out, "C", _CFG)
        )
        ids = [f.finding_id for f in all_findings]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 10. Insufficient evidence
# ---------------------------------------------------------------------------

class TestInsufficientEvidence:
    """Scenario 10: missing data, empty graph, or unconfigured DB."""

    def test_empty_incoming_no_fan_in(self):
        assert detect_fan_in([], "A", _CFG) == []

    def test_empty_outgoing_no_fan_out(self):
        assert detect_fan_out([], "A", _CFG) == []

    def test_empty_paths_no_layering(self):
        assert detect_layering([], "A", _CFG) == []

    def test_empty_cluster_no_cluster_finding(self):
        assert detect_suspicious_cluster([], "A", _CFG) == []

    def test_rapid_forwarding_no_data(self):
        assert detect_rapid_forwarding([], [], "A", _CFG) == []

    def test_mule_empty_both(self):
        assert detect_mule_like([], [], "A", _CFG) == []

    def test_structuring_empty(self):
        assert detect_structuring([], "A", _CFG) == []


# ---------------------------------------------------------------------------
# Config: boundary conditions and env loading
# ---------------------------------------------------------------------------

class TestAgent3Config:
    def test_default_values(self):
        cfg = Agent3Config()
        assert cfg.min_layering_hops == 3
        assert cfg.fan_in_min_sources == 3
        assert cfg.fan_window_hours == 24.0
        assert cfg.layering_min_amount_retention == 0.80
        assert cfg.rapid_forwarding_window_minutes == 120.0

    def test_from_env_uses_defaults_when_no_env(self, monkeypatch):
        for k in [
            "SENTINEL_A3_MAX_LAYERING_HOPS",
            "SENTINEL_A3_FAN_IN_MIN_SOURCES",
        ]:
            monkeypatch.delenv(k, raising=False)
        cfg = Agent3Config.from_env()
        assert cfg.max_layering_hops == 5
        assert cfg.fan_in_min_sources == 3

    def test_from_env_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_A3_FAN_IN_MIN_SOURCES", "5")
        cfg = Agent3Config.from_env()
        assert cfg.fan_in_min_sources == 5

    def test_config_is_frozen(self):
        cfg = Agent3Config()
        with pytest.raises((AttributeError, TypeError)):
            cfg.fan_in_min_sources = 99  # type: ignore


# ---------------------------------------------------------------------------
# Output schema: validation and structure
# ---------------------------------------------------------------------------

class TestAgent3OutputSchema:
    def test_minimal_output_constructs(self):
        out = Agent3Output(status=Agent3Status.COMPLETE)
        assert out.finding_count == 0
        assert out.findings == []
        assert out.status == Agent3Status.COMPLETE

    def test_finding_count_field(self):
        finding = NetworkFinding(
            pattern_type=NetworkPatternType.FAN_IN,
            rule_id="AGENT3.FAN_IN.v2",
            subject_account_id="ACC_A",
            explanation="test",
        )
        out = Agent3Output(
            status=Agent3Status.COMPLETE,
            findings=[finding],
            finding_count=1,
        )
        assert out.finding_count == 1

    def test_output_is_frozen(self):
        from pydantic import ValidationError
        out = Agent3Output(status=Agent3Status.COMPLETE)
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            out.status = Agent3Status.FAILED  # type: ignore

    def test_finding_is_frozen(self):
        from pydantic import ValidationError
        f = NetworkFinding(
            pattern_type=NetworkPatternType.FAN_OUT,
            rule_id="AGENT3.FAN_OUT.v2",
            subject_account_id="ACC_A",
            explanation="test",
        )
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            f.subject_account_id = "OTHER"  # type: ignore

    def test_analysis_note_in_output(self):
        out = Agent3Output(status=Agent3Status.COMPLETE)
        assert "Agent 3" in out.analysis_note
        assert any(phrase in out.analysis_note for phrase in [
            "does NOT produce",
            "NOT produce",
            "no final",
        ])

    def test_empty_findings_semantics_in_unavailable(self):
        """UNAVAILABLE + empty findings must be clearly documented."""
        out = Agent3Output(
            status=Agent3Status.UNAVAILABLE,
            warnings=["Account not in graph."],
        )
        assert out.findings == []
        assert out.status == Agent3Status.UNAVAILABLE

    def test_finding_has_query_timestamp(self):
        f = NetworkFinding(
            pattern_type=NetworkPatternType.FAN_IN,
            rule_id="AGENT3.FAN_IN.v2",
            subject_account_id="A",
            explanation="test",
        )
        assert f.query_timestamp_utc is not None


# ---------------------------------------------------------------------------
# Agent: pipeline integration (mocked graph)
# ---------------------------------------------------------------------------

def _make_mock_manager(
    *,
    sender_exists: bool = True,
    receiver_exists: bool = True,
    outgoing: list = None,
    incoming: list = None,
    cluster: list = None,
    paths: list = None,
    graph_transfers: int = None,
):
    """Build a mock Neo4jConnectionManager returning specified data."""
    mgr = MagicMock()
    mgr.connect.return_value = None
    mgr.verify_connectivity.return_value = None
    mgr.close.return_value = None

    # session() as context manager
    mock_session = MagicMock()
    mgr.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mgr.session.return_value.__exit__ = MagicMock(return_value=False)

    def _run_result(data_rows):
        r = MagicMock()
        r.data.return_value = data_rows or []
        return r

    # Map each query to its result based on keywords in the cypher
    def run_side_effect(cypher, **kwargs):
        c = cypher.strip().upper()
        if "COUNT(A)" in c:
            count = 1 if (
                (kwargs.get("account_id") == "ACC_A" and sender_exists) or
                (kwargs.get("account_id") == "ACC_B" and receiver_exists)
            ) else 0
            r = MagicMock()
            r.single.return_value = {"count": count}
            return r
        if "COUNT(R) AS TRANSFERS" in c:
            return _run_result([] if graph_transfers is None else [{"transfers": graph_transfers}])
        # v2 queries: data is attached to the sender (ACC_A) only
        is_sender = kwargs.get("account_id") == "ACC_A"
        if "R0:TRANSFERRED_TO" in c:
            # forward layering query returns `paths`; backward returns nothing
            return _run_result((paths or []) if "MATCH P = (R)" in c else [])
        if "TRANSFERRED_TO*" in c:
            return _run_result((cluster or []) if is_sender else [])
        if "-[R:TRANSFERRED_TO]->(B:ACCOUNT)" in c and "TIMESTAMP_UTC >=" in c:
            return _run_result((outgoing or []) if is_sender else [])
        if "(B:ACCOUNT)-[R:TRANSFERRED_TO]->(A:ACCOUNT" in c and "TIMESTAMP_UTC >=" in c:
            return _run_result((incoming or []) if is_sender else [])
        # loader MERGE queries
        return _run_result([])

    mock_session.run = MagicMock(side_effect=run_side_effect)
    mock_session.execute_write = MagicMock(return_value=None)

    return mgr


class TestNetworkAnalyserAgentPipeline:
    """Integration tests using mocked Neo4j manager."""

    def _agent(self, mgr=None, **cfg_kwargs) -> NetworkAnalyserAgent:
        cfg = Agent3Config(**cfg_kwargs) if cfg_kwargs else _CFG
        return NetworkAnalyserAgent(config=cfg, connection_manager=mgr)

    def test_callable_returns_updated_state(self):
        mgr = _make_mock_manager()
        agent = self._agent(mgr=mgr)
        tx = _make_tx()
        state = {"transaction": tx}
        new_state = agent(state)
        assert "agent3_output" in new_state
        assert "transaction" in new_state  # existing keys preserved
        assert isinstance(new_state["agent3_output"], Agent3Output)

    def test_no_transaction_in_state_gives_validation_error(self):
        agent = self._agent(mgr=_make_mock_manager())
        new_state = agent({})
        assert new_state["agent3_output"].status == Agent3Status.VALIDATION_ERROR

    def test_missing_sender_id_gives_validation_error(self):
        tx = CanonicalTransaction(
            raw_record_id="TX1",
            source_dataset=DataSource.INDIA_SYNTHETIC,
            amount=Decimal("100"),
            currency="INR",
            timestamp=_T0,
            channel=TransactionChannel.UPI,
            status=TransactionStatus.SUCCESS,
            sender=AccountInfo(account_id=None),
            receiver=AccountInfo(account_id="ACC_B"),
        )
        agent = self._agent(mgr=_make_mock_manager())
        result = agent.analyse(tx)
        assert result.status == Agent3Status.VALIDATION_ERROR

    def test_empty_graph_is_partial_not_clean(self):
        mgr = _make_mock_manager(graph_transfers=3, outgoing=[], incoming=[], cluster=[], paths=[])
        result = self._agent(mgr=mgr).analyse(_make_tx())
        assert result.status == Agent3Status.PARTIAL
        assert result.findings == []
        assert any("appears empty or not loaded" in w for w in result.warnings)

    def test_populated_graph_stays_complete(self):
        mgr = _make_mock_manager(graph_transfers=10_000, outgoing=[], incoming=[], cluster=[], paths=[])
        result = self._agent(mgr=mgr).analyse(_make_tx())
        assert result.status == Agent3Status.COMPLETE
        assert not any("appears empty" in w for w in result.warnings)

    def test_min_graph_transfers_configurable(self):
        mgr = _make_mock_manager(graph_transfers=3, outgoing=[], incoming=[], cluster=[], paths=[])
        result = self._agent(mgr=mgr, min_graph_transfers=0).analyse(_make_tx())
        assert result.status == Agent3Status.COMPLETE

    def test_account_not_in_graph_gives_unavailable(self):
        mgr = _make_mock_manager(sender_exists=False, receiver_exists=False)
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        assert result.status == Agent3Status.UNAVAILABLE
        assert result.sender_in_graph is False
        assert result.receiver_in_graph is False

    def test_complete_status_no_patterns(self):
        mgr = _make_mock_manager(
            sender_exists=True, receiver_exists=True,
            outgoing=[], incoming=[], cluster=[], paths=[],
        )
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        assert result.status == Agent3Status.COMPLETE
        assert result.findings == []
        assert result.finding_count == 0

    def test_fan_in_detected_via_agent(self):
        inc = [_in_row(f"SRC{i}", tx_id=f"IN{i}") for i in range(3)]
        mgr = _make_mock_manager(incoming=inc)
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        fan_in_findings = [f for f in result.findings if f.pattern_type == NetworkPatternType.FAN_IN]
        assert len(fan_in_findings) == 1

    def test_fan_out_detected_via_agent(self):
        out = [_out_row(f"DST{i}", tx_id=f"OUT{i}") for i in range(3)]
        mgr = _make_mock_manager(outgoing=out)
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        fan_out = [f for f in result.findings if f.pattern_type == NetworkPatternType.FAN_OUT]
        assert len(fan_out) == 1

    def test_output_fields_populated(self):
        mgr = _make_mock_manager()
        agent = self._agent(mgr=mgr)
        tx = _make_tx(raw_id="TXTEST", sender_id="ACC_A", receiver_id="ACC_B")
        result = agent.analyse(tx)
        assert result.transaction_id == "TXTEST"
        assert result.sender_account_id == "ACC_A"
        assert result.receiver_account_id == "ACC_B"
        assert result.source_dataset == "INDIA_SYNTHETIC"
        assert result.analysed_at_utc is not None

    def test_prior_agent_state_preserved(self):
        """Existing state keys must not be removed by the agent call."""
        mgr = _make_mock_manager()
        agent = self._agent(mgr=mgr)
        mock_a1 = MagicMock()
        mock_a2 = MagicMock()
        state = {
            "transaction": _make_tx(),
            "agent1_output": mock_a1,
            "agent2_output": mock_a2,
            "custom_key": "preserved",
        }
        new_state = agent(state)
        assert new_state["agent1_output"] is mock_a1
        assert new_state["agent2_output"] is mock_a2
        assert new_state["custom_key"] == "preserved"

    def test_neo4j_config_error_gives_unavailable(self):
        from src.graph.connection import Neo4jConfigError
        agent = NetworkAnalyserAgent(config=_CFG)
        with patch("src.agents.agent3.network_analyser.Neo4jConnectionManager") as mock_cls:
            mock_mgr = MagicMock()
            mock_mgr.connect.side_effect = Neo4jConfigError("not configured")
            mock_cls.return_value = mock_mgr
            result = agent.analyse(_make_tx())
        assert result.status == Agent3Status.UNAVAILABLE
        assert any("not configured" in e.lower() or "neo4j" in e.lower()
                   for e in result.errors)

    def test_no_credentials_in_errors(self):
        """Error messages must not contain passwords or connection strings."""
        from src.graph.connection import Neo4jConnectivityError
        agent = NetworkAnalyserAgent(config=_CFG)
        with patch("src.agents.agent3.network_analyser.Neo4jConnectionManager") as mock_cls:
            mock_mgr = MagicMock()
            mock_mgr.connect.side_effect = Neo4jConnectivityError("unreachable")
            mock_cls.return_value = mock_mgr
            result = agent.analyse(_make_tx())
        for err in result.errors:
            assert "password" not in err.lower()
            assert "neo4j+s://" not in err.lower()

    def test_graph_ingestion_flag_set(self):
        mgr = _make_mock_manager()
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        # Ingestion was attempted — flag should be True if loader succeeded
        # or False if it failed with a warning
        assert isinstance(result.graph_ingestion_performed, bool)

    def test_detectors_run_list_populated(self):
        mgr = _make_mock_manager(outgoing=[], incoming=[], cluster=[], paths=[])
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        assert len(result.detectors_run) > 0

    def test_rapid_forwarding_detected_via_agent(self):
        inc = [_in_row("SRC1", ts_offset_min=0, tx_id="IN1")]
        out = [_out_row("DST1", ts_offset_min=30, tx_id="OUT1")]
        mgr = _make_mock_manager(incoming=inc, outgoing=out)
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        rf = [f for f in result.findings if f.pattern_type == NetworkPatternType.RAPID_FORWARDING]
        assert len(rf) >= 1

    def test_structuring_detected_via_agent(self):
        out = [_out_row("B", amount=49500, ts_offset_min=i * 60, tx_id=f"T{i}") for i in range(3)]
        mgr = _make_mock_manager(outgoing=out)
        agent = self._agent(mgr=mgr)
        result = agent.analyse(_make_tx())
        st = [f for f in result.findings if f.pattern_type == NetworkPatternType.STRUCTURING]
        assert len(st) >= 1


# ---------------------------------------------------------------------------
# Rule IDs and detection parameters preserved
# ---------------------------------------------------------------------------

class TestFindingProvenanceAndExplainability:
    def test_layering_rule_id(self):
        paths = [_path_row(["A", "B", "C"], 2)]
        findings = detect_layering(paths, "A", _CFG)
        assert findings[0].rule_id == "AGENT3.LAYERING.v2"

    def test_fan_in_rule_id(self):
        inc = [_in_row(f"SRC{i}", tx_id=f"T{i}") for i in range(3)]
        findings = detect_fan_in(inc, "R", _CFG)
        assert findings[0].rule_id == "AGENT3.FAN_IN.v2"

    def test_fan_out_rule_id(self):
        out = [_out_row(f"DST{i}", tx_id=f"T{i}") for i in range(3)]
        findings = detect_fan_out(out, "S", _CFG)
        assert findings[0].rule_id == "AGENT3.FAN_OUT.v2"

    def test_structuring_rule_id(self):
        out = [_out_row("B", amount=49500, ts_offset_min=i * 60, tx_id=f"T{i}") for i in range(3)]
        findings = detect_structuring(out, "A", _CFG)
        assert findings[0].rule_id == "AGENT3.STRUCTURING.v2"

    def test_detection_parameters_preserved(self):
        inc = [_in_row(f"SRC{i}", tx_id=f"T{i}") for i in range(3)]
        findings = detect_fan_in(inc, "R", _CFG)
        assert "fan_in_min_sources" in findings[0].detection_parameters
        assert findings[0].detection_parameters["fan_in_min_sources"] == 3

    def test_heuristic_score_always_in_range(self):
        inc = [_in_row(f"S{i}", tx_id=f"T{i}") for i in range(5)]
        out = [_out_row(f"D{i}", ts_offset_min=i * 10, tx_id=f"TO{i}") for i in range(5)]
        for fn in [
            detect_fan_in(inc, "A", _CFG),
            detect_fan_out(out, "A", _CFG),
            detect_mule_like(inc, out, "A", _CFG),
        ]:
            for f in fn:
                assert 0.0 <= f.heuristic_score <= 1.0

    def test_explanation_not_fraud_determination(self):
        """Explanations must not claim fraud was proved."""
        inc = [_in_row(f"S{i}", tx_id=f"T{i}") for i in range(3)]
        findings = detect_fan_in(inc, "R", _CFG)
        expl = findings[0].explanation.lower()
        # Must contain a caveat
        assert any(phrase in expl for phrase in [
            "not a fraud determination",
            "indicator",
            "heuristic",
            "structural",
        ])
