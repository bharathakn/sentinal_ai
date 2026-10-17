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
        Default: 4

    min_layering_hops : int
        Minimum chain length (hops) required to flag a layering pattern.
        A chain of 1 hop is a direct transfer; layering requires ≥2.
        Default: 2

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
        Default: 2

    cluster_min_accounts : int
        Minimum number of accounts in a connected component for the
        suspicious-cluster detector to examine it.
        Default: 4

    cluster_min_edges : int
        Minimum number of transfer relationships within a candidate cluster.
        Default: 4

    transfer_query_limit : int
        Maximum number of transfer rows fetched per account query.
        Prevents unbounded memory usage on accounts with many transfers.
        Default: 200

    layering_path_limit : int
        Maximum number of layering paths to return per search.
        Default: 5
    """

    max_layering_hops: int = 4
    min_layering_hops: int = 2
    layering_max_elapsed_hours: float = 72.0

    fan_in_min_sources: int = 3
    fan_out_min_destinations: int = 3

    structuring_min_transfers: int = 3
    structuring_window_hours: float = 24.0

    rapid_forwarding_window_minutes: float = 120.0

    mule_min_incoming_sources: int = 2
    mule_min_outgoing_destinations: int = 2

    cluster_min_accounts: int = 4
    cluster_min_edges: int = 4

    transfer_query_limit: int = 200
    layering_path_limit: int = 5

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
            max_layering_hops=_int("SENTINEL_A3_MAX_LAYERING_HOPS", 4),
            min_layering_hops=_int("SENTINEL_A3_MIN_LAYERING_HOPS", 2),
            layering_max_elapsed_hours=_float("SENTINEL_A3_LAYERING_MAX_ELAPSED_HOURS", 72.0),
            fan_in_min_sources=_int("SENTINEL_A3_FAN_IN_MIN_SOURCES", 3),
            fan_out_min_destinations=_int("SENTINEL_A3_FAN_OUT_MIN_DESTINATIONS", 3),
            structuring_min_transfers=_int("SENTINEL_A3_STRUCTURING_MIN_TRANSFERS", 3),
            structuring_window_hours=_float("SENTINEL_A3_STRUCTURING_WINDOW_HOURS", 24.0),
            rapid_forwarding_window_minutes=_float("SENTINEL_A3_RAPID_FWD_WINDOW_MINUTES", 120.0),
            mule_min_incoming_sources=_int("SENTINEL_A3_MULE_MIN_INCOMING", 2),
            mule_min_outgoing_destinations=_int("SENTINEL_A3_MULE_MIN_OUTGOING", 2),
            cluster_min_accounts=_int("SENTINEL_A3_CLUSTER_MIN_ACCOUNTS", 4),
            cluster_min_edges=_int("SENTINEL_A3_CLUSTER_MIN_EDGES", 4),
            transfer_query_limit=_int("SENTINEL_A3_TRANSFER_QUERY_LIMIT", 200),
            layering_path_limit=_int("SENTINEL_A3_LAYERING_PATH_LIMIT", 5),
        )
