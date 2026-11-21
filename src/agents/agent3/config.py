"""
Sentinel AI — Agent 3: Network Analyser Configuration

Centralises all tunable detection thresholds and traversal limits for
Agent 3. All parameters are documented engineering heuristics suitable for
the synthetic prototype. They are NOT calibrated fraud probabilities and
NOT regulatory reporting thresholds.

Design rules
------------
* Every parameter has a documented rationale.
* All values have conservative defaults safe for the synthetic test scenarios.
* Parameters are accessible both programmatically and via environment variables
  so that the detection rules can be tuned without code changes.
* No threshold here implies a legal determination or regulatory obligation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Agent3Config:
    """
    Tunable configuration for Agent 3 network-pattern detectors.

    All thresholds are ENGINEERING HEURISTICS for the Sentinel AI prototype.
    They are NOT:
      - Calibrated fraud-detection probabilities
      - Regulatory reporting thresholds (e.g. PMLA, FATF, FinCEN)
      - Legally authoritative determinations

    Parameters
    ----------
    max_layering_hops : int
        Maximum number of transfer hops to follow when searching for
        layering chains. Higher values may find deeper chains but increase
        query cost. Hard-capped at 6 by the Phase 7 query layer.
        Default: 5 (v2)

    min_layering_hops : int
        Minimum chain length (hops) required to flag a layering pattern.
        A chain of 1 hop is a direct transfer; layering requires ≥2.
        Default: 3 (v2; was 2)

    layering_max_elapsed_hours : float
        Maximum elapsed time (hours) between the first and last transfer
        in a chain for it to be considered a rapid-layering indicator.
        Chains where timestamps are missing are reported without this check.
        Default: 72.0

    fan_in_min_sources : int
        Minimum number of distinct source accounts sending to a single
        recipient within the observation window to flag fan-in.
        Default: 3

    fan_out_min_destinations : int
        Minimum number of distinct recipient accounts receiving from a
        single sender within the observation window to flag fan-out.
        Default: 3

    structuring_min_transfers : int
        Minimum number of transfers by the same sender within the
        structuring time window to trigger the prototype heuristic check.
        Default: 3

    structuring_window_hours : float
        Time window (hours) within which repeated transfers are examined
        for the structuring prototype heuristic.
        Default: 24.0

    rapid_forwarding_window_minutes : float
        Maximum elapsed time (minutes) between an incoming transfer and a
        subsequent outgoing transfer from the same account for the event to
        be flagged as rapid forwarding. Missing timestamps are excluded.
        Default: 120.0  (2 hours)

    mule_min_incoming_sources : int
        Minimum number of distinct accounts sending funds into a candidate
        mule account within the observation window.
        Default: 2

    mule_min_outgoing_destinations : int
        Minimum number of distinct accounts receiving funds from a candidate
        mule account within the observation window.
        Default: 1 (v2; was 2)

    cluster_min_accounts : int
        Minimum number of accounts in a connected component for the
        suspicious-cluster detector to examine it.
        Default: 3 (v2; was 4)

    cluster_min_edges : int
        Minimum number of transfer relationships within a candidate cluster.
        Default: 3 (v2; was 4)

    min_graph_transfers : int
        If the whole graph holds fewer TRANSFERRED_TO relationships than this,
        it is treated as empty / not loaded: status PARTIAL with a warning,
        because "no patterns found" would otherwise read as a clean result.
        Default: 100.

    transfer_query_limit : int
        Maximum number of transfer rows fetched per account query.
        Prevents unbounded memory usage on accounts with many transfers.
        Default: 200

    layering_path_limit : int
        Maximum number of layering paths to return per search.
        Default: 5

    v2 temporal parameters (Phase 9.5)
    ----------------------------------
    v1 detectors were timeless and structural; on a realistically dense graph
    every account matched every pattern. v2 anchors analysis on the
    investigated transaction's timestamp T.

    lookback_hours / horizon_hours
        Analysis window [T - lookback, T + horizon]. The horizon models an
        investigation performed shortly after the alert, so onward movement
        of the funds is visible. Defaults: 168 h / 24 h.
    fan_window_hours
        Fan-in / fan-out count distinct counterparties within any window of
        this length. Default: 24 h.
    layering_hop_max_gap_hours, layering_min_amount_retention
        A layering chain is time-ordered; each hop follows the previous within
        the gap and carries at least this fraction of its amount.
        Defaults: 6 h, 0.80. min_layering_hops is now 3, max 5.
    structuring_round_unit, structuring_proximity_pct
        Structuring counts outgoing transfers just below a multiple of the
        unit (within the proximity fraction). An engineering heuristic, NOT a
        regulatory reporting threshold. Defaults: 50,000, 0.10.
    rapid_forwarding_min_ratio
        Outgoing amount must be at least this fraction of the incoming amount.
        Default: 0.5.
    mule_window_hours, mule_min_passthrough_ratio
        Mule-like: >= mule_min_incoming_sources sources, then outgoing >= ratio
        of the incoming total, within the window. Defaults: 48 h, 0.70;
        mule_min_outgoing_destinations is now 1.
    cluster_max_cycle_length, cluster_window_hours
        Suspicious cluster = time-ordered cycle of cluster_min_accounts..max
        accounts returning to the subject within the window.
        Defaults: 3..6 accounts, 72 h. cluster_min_edges is the minimum cycle
        length in transfers.
    """

    max_layering_hops: int = 5
    min_layering_hops: int = 3
    layering_max_elapsed_hours: float = 72.0

    fan_in_min_sources: int = 3
    fan_out_min_destinations: int = 3

    structuring_min_transfers: int = 3
    structuring_window_hours: float = 24.0

    rapid_forwarding_window_minutes: float = 120.0

    mule_min_incoming_sources: int = 2
    mule_min_outgoing_destinations: int = 1

    cluster_min_accounts: int = 3
    cluster_min_edges: int = 3

    transfer_query_limit: int = 200
    min_graph_transfers: int = 100
    layering_path_limit: int = 5

    # --- v2 temporal parameters (Phase 9.5) ---
    lookback_hours: float = 168.0
    horizon_hours: float = 24.0
    fan_window_hours: float = 24.0
    layering_hop_max_gap_hours: float = 6.0
    layering_min_amount_retention: float = 0.80
    structuring_round_unit: float = 50000.0
    structuring_proximity_pct: float = 0.10
    rapid_forwarding_min_ratio: float = 0.50
    mule_window_hours: float = 48.0
    mule_min_passthrough_ratio: float = 0.70
    cluster_max_cycle_length: int = 6
    cluster_window_hours: float = 72.0

    @classmethod
    def from_env(cls) -> "Agent3Config":
        """
        Build configuration from environment variables, falling back to defaults.

        Environment variables (all optional):
          SENTINEL_A3_MAX_LAYERING_HOPS
          SENTINEL_A3_MIN_LAYERING_HOPS
          SENTINEL_A3_LAYERING_MAX_ELAPSED_HOURS
          SENTINEL_A3_FAN_IN_MIN_SOURCES
          SENTINEL_A3_FAN_OUT_MIN_DESTINATIONS
          SENTINEL_A3_STRUCTURING_MIN_TRANSFERS
          SENTINEL_A3_STRUCTURING_WINDOW_HOURS
          SENTINEL_A3_RAPID_FWD_WINDOW_MINUTES
          SENTINEL_A3_MULE_MIN_INCOMING
          SENTINEL_A3_MULE_MIN_OUTGOING
          SENTINEL_A3_CLUSTER_MIN_ACCOUNTS
          SENTINEL_A3_CLUSTER_MIN_EDGES
          SENTINEL_A3_TRANSFER_QUERY_LIMIT
          SENTINEL_A3_LAYERING_PATH_LIMIT
        """
        def _int(key: str, default: int) -> int:
            return int(os.environ.get(key, default))

        def _float(key: str, default: float) -> float:
            return float(os.environ.get(key, default))

        return cls(
            max_layering_hops=_int("SENTINEL_A3_MAX_LAYERING_HOPS", 5),
            min_layering_hops=_int("SENTINEL_A3_MIN_LAYERING_HOPS", 3),
            layering_max_elapsed_hours=_float("SENTINEL_A3_LAYERING_MAX_ELAPSED_HOURS", 72.0),
            fan_in_min_sources=_int("SENTINEL_A3_FAN_IN_MIN_SOURCES", 3),
            fan_out_min_destinations=_int("SENTINEL_A3_FAN_OUT_MIN_DESTINATIONS", 3),
            structuring_min_transfers=_int("SENTINEL_A3_STRUCTURING_MIN_TRANSFERS", 3),
            structuring_window_hours=_float("SENTINEL_A3_STRUCTURING_WINDOW_HOURS", 24.0),
            rapid_forwarding_window_minutes=_float("SENTINEL_A3_RAPID_FWD_WINDOW_MINUTES", 120.0),
            mule_min_incoming_sources=_int("SENTINEL_A3_MULE_MIN_INCOMING", 2),
            mule_min_outgoing_destinations=_int("SENTINEL_A3_MULE_MIN_OUTGOING", 1),
            cluster_min_accounts=_int("SENTINEL_A3_CLUSTER_MIN_ACCOUNTS", 3),
            cluster_min_edges=_int("SENTINEL_A3_CLUSTER_MIN_EDGES", 3),
            transfer_query_limit=_int("SENTINEL_A3_TRANSFER_QUERY_LIMIT", 200),
            min_graph_transfers=_int("SENTINEL_A3_MIN_GRAPH_TRANSFERS", 100),
            layering_path_limit=_int("SENTINEL_A3_LAYERING_PATH_LIMIT", 5),
            lookback_hours=_float("SENTINEL_A3_LOOKBACK_HOURS", 168.0),
            horizon_hours=_float("SENTINEL_A3_HORIZON_HOURS", 24.0),
            fan_window_hours=_float("SENTINEL_A3_FAN_WINDOW_HOURS", 24.0),
            layering_hop_max_gap_hours=_float("SENTINEL_A3_LAYERING_HOP_MAX_GAP_HOURS", 6.0),
            layering_min_amount_retention=_float("SENTINEL_A3_LAYERING_MIN_RETENTION", 0.80),
            structuring_round_unit=_float("SENTINEL_A3_STRUCTURING_ROUND_UNIT", 50000.0),
            structuring_proximity_pct=_float("SENTINEL_A3_STRUCTURING_PROXIMITY_PCT", 0.10),
            rapid_forwarding_min_ratio=_float("SENTINEL_A3_RAPID_FWD_MIN_RATIO", 0.50),
            mule_window_hours=_float("SENTINEL_A3_MULE_WINDOW_HOURS", 48.0),
            mule_min_passthrough_ratio=_float("SENTINEL_A3_MULE_MIN_PASSTHROUGH", 0.70),
            cluster_max_cycle_length=_int("SENTINEL_A3_CLUSTER_MAX_CYCLE", 6),
            cluster_window_hours=_float("SENTINEL_A3_CLUSTER_WINDOW_HOURS", 72.0),
        )
