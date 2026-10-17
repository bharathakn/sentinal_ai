"""
Sentinel AI — Agent 3: Network Analyser Output Schema

Defines the validated Pydantic output contract for Agent 3.

Design rules
------------
* Every finding carries the rule_id, relevant account IDs, transaction IDs,
  amounts, timestamps, and a plain-language explanation.
* An empty findings list means the supported checks completed and found no
  patterns — it does NOT mean a database failure or incomplete analysis.
* Failed or unavailable checks are reflected in status and errors, never
  silently suppressed or misrepresented as clean results.
* No field in this schema represents a final fraud determination.
* Confidence indicators are explicitly labelled as prototype heuristics.
* All timestamps are UTC ISO-8601 strings (matching the graph property format).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Agent3Status(str, Enum):
    """Overall status of the Agent 3 network analysis run."""

    COMPLETE = "COMPLETE"
    """All enabled detectors ran successfully; findings (if any) are reliable."""

    PARTIAL = "PARTIAL"
    """Some detectors ran; others failed or were skipped. Findings are incomplete."""

    UNAVAILABLE = "UNAVAILABLE"
    """No graph data was available (missing accounts, empty graph, or unconfigured DB)."""

    FAILED = "FAILED"
    """Critical failure: graph connectivity lost or invalid inputs prevented any analysis."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Invalid or missing inputs — analysis could not begin."""


class NetworkPatternType(str, Enum):
    """Supported network-pattern indicators detected by Agent 3."""

    LAYERING = "LAYERING"
    """Multi-hop fund movement through intermediary accounts."""

    STRUCTURING = "STRUCTURING"
    """Repeated transfers meeting prototype heuristic criteria."""

    FAN_IN = "FAN_IN"
    """Multiple distinct sources sending to a common recipient."""

    FAN_OUT = "FAN_OUT"
    """One sender distributing to multiple distinct recipients."""

    MULE_LIKE = "MULE_LIKE"
    """Account receives from multiple sources then forwards onward — heuristic indicator."""

    RAPID_FORWARDING = "RAPID_FORWARDING"
    """Outgoing transfers occur shortly after incoming funds are received."""

    SUSPICIOUS_CLUSTER = "SUSPICIOUS_CLUSTER"
    """Dense or cyclically-connected account group meeting cluster criteria."""


# ---------------------------------------------------------------------------
# Supporting evidence models
# ---------------------------------------------------------------------------


class TransferRef(BaseModel):
    """Reference to a single TRANSFERRED_TO relationship in the graph."""

    model_config = ConfigDict(frozen=True)

    tx_graph_id: Optional[str] = Field(
        default=None,
        description="Graph idempotency key: raw_record_id::source_dataset.",
    )
    raw_record_id: Optional[str] = Field(
        default=None,
        description="Original transaction identifier from the source dataset.",
    )
    from_account_id: Optional[str] = Field(default=None)
    to_account_id: Optional[str] = Field(default=None)
    amount: Optional[float] = Field(default=None, description="Transfer amount.")
    amount_str: Optional[str] = Field(
        default=None, description="Amount as decimal string (precision-preserving)."
    )
    currency: Optional[str] = Field(default=None)
    timestamp_utc: Optional[str] = Field(
        default=None, description="UTC ISO-8601 timestamp string."
    )
    channel: Optional[str] = Field(default=None)


class LayeringPath(BaseModel):
    """A single multi-hop transfer path detected as a layering indicator."""

    model_config = ConfigDict(frozen=True)

    account_ids: list[str] = Field(
        description="Ordered list of account IDs along the path (sender → ... → final receiver)."
    )
    hop_count: int = Field(description="Number of transfer hops in the path.")
    transfers: list[TransferRef] = Field(
        default_factory=list,
        description="Transfer references along this path.",
    )
    elapsed_hours: Optional[float] = Field(
        default=None,
        description=(
            "Elapsed hours from first to last transfer in path. "
            "None when timestamps are missing."
        ),
    )


class NetworkFinding(BaseModel):
    """
    A single detected network-pattern finding.

    Each finding must be supported by actual graph relationships and their
    properties. It includes enough information for Agent 4 to evaluate the
    finding without repeating graph traversal.

    IMPORTANT: A finding is a heuristic indicator, NOT a fraud determination.
    The rule_id and detection parameters are preserved so findings are
    explainable and auditable.
    """

    model_config = ConfigDict(frozen=True)

    finding_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this finding instance.",
    )
    pattern_type: NetworkPatternType = Field(
        description="Category of the detected pattern."
    )
    rule_id: str = Field(
        description=(
            "Identifier of the detection rule that produced this finding. "
            "Format: AGENT3.<PATTERN_TYPE>.<VERSION>. "
            "Enables traceability and threshold review."
        )
    )
    subject_account_id: str = Field(
        description="Primary account ID under investigation for this finding."
    )
    related_account_ids: list[str] = Field(
        default_factory=list,
        description="Other account IDs involved in this finding.",
    )
    supporting_transfers: list[TransferRef] = Field(
        default_factory=list,
        description="Transfer relationships that support this finding.",
    )
    layering_paths: list[LayeringPath] = Field(
        default_factory=list,
        description="Populated for LAYERING findings only.",
    )
    transfer_count: Optional[int] = Field(
        default=None,
        description="Number of transfers relevant to this finding.",
    )
    hop_count: Optional[int] = Field(
        default=None,
        description="Number of hops in the path. Populated for LAYERING findings.",
    )
    distinct_counterparty_count: Optional[int] = Field(
        default=None,
        description="Number of distinct counterparty accounts involved.",
    )
    total_amount: Optional[float] = Field(
        default=None,
        description="Aggregate transfer amount associated with this finding.",
    )
    currency: Optional[str] = Field(
        default=None,
        description="Currency of the transfers (from graph data).",
    )
    elapsed_minutes: Optional[float] = Field(
        default=None,
        description=(
            "Time elapsed (minutes) between relevant events. "
            "Used for rapid-forwarding and structuring findings."
        ),
    )
    heuristic_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "PROTOTYPE heuristic indicator score in [0, 1]. "
            "NOT a calibrated fraud probability. "
            "NOT a regulatory or legal determination. "
            "Derived from detection rule parameters and observed values."
        ),
    )
    explanation: str = Field(
        description=(
            "Plain-language explanation of the finding and which conditions were met. "
            "Cites the actual graph evidence (accounts, transfers, amounts, timing). "
            "Does not claim to prove fraud."
        )
    )
    detection_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "The configured threshold values used by the detection rule "
            "that produced this finding. Preserved for auditability."
        ),
    )
    query_timestamp_utc: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 timestamp when this finding was produced.",
    )


# ---------------------------------------------------------------------------
# Main output model
# ---------------------------------------------------------------------------


class Agent3Output(BaseModel):
    """
    Structured output for Agent 3 (Network Analyser).

    Contains all detected network-pattern findings from the Neo4j graph,
    plus analysis status, provenance, and data-quality indicators.

    Downstream agents (Agent 4, Agent 5) must:
    - Check `status` before consuming findings.
    - Not treat UNAVAILABLE or FAILED as a clean network result.
    - Not treat an empty findings list as confirming absence of fraud
      when status is PARTIAL, UNAVAILABLE, or FAILED.
    - Treat heuristic_score as a prototype signal, not a fraud probability.
    """

    model_config = ConfigDict(frozen=True)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    agent3_run_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this Agent 3 run.",
    )
    transaction_id: Optional[str] = Field(
        default=None,
        description="raw_record_id from the subject CanonicalTransaction.",
    )
    source_dataset: Optional[str] = Field(
        default=None,
        description="source_dataset from the subject CanonicalTransaction.",
    )
    sender_account_id: Optional[str] = Field(
        default=None,
        description="sender.account_id from the subject transaction.",
    )
    receiver_account_id: Optional[str] = Field(
        default=None,
        description="receiver.account_id from the subject transaction.",
    )
    analysed_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when Agent 3 completed its analysis.",
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status: Agent3Status = Field(
        description="Overall analysis status. Check before consuming findings."
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-fatal warnings: missing timestamps, partial graph data, "
            "skipped detectors. Non-empty does not mean analysis failed."
        ),
    )
    errors: list[str] = Field(
        default_factory=list,
        description=(
            "Error messages. Non-empty when status is FAILED. "
            "Sanitised — credentials and stack traces are excluded."
        ),
    )
    detectors_run: list[str] = Field(
        default_factory=list,
        description="Names of detectors that ran successfully.",
    )
    detectors_skipped: list[str] = Field(
        default_factory=list,
        description="Names of detectors that were skipped or failed.",
    )

    # ------------------------------------------------------------------
    # Graph context
    # ------------------------------------------------------------------
    sender_in_graph: Optional[bool] = Field(
        default=None,
        description="True if the sender account was found in the graph.",
    )
    receiver_in_graph: Optional[bool] = Field(
        default=None,
        description="True if the receiver account was found in the graph.",
    )
    graph_ingestion_performed: bool = Field(
        default=False,
        description=(
            "True if Agent 3 ingested the subject transaction into the graph "
            "before running detection queries."
        ),
    )

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------
    findings: list[NetworkFinding] = Field(
        default_factory=list,
        description=(
            "Detected network-pattern findings. "
            "An empty list means all enabled detectors completed and found "
            "no patterns meeting the configured thresholds. "
            "An empty list with status=UNAVAILABLE/FAILED/PARTIAL means "
            "the investigation was incomplete — do NOT treat as clean."
        ),
    )
    finding_count: int = Field(
        default=0,
        description="Total number of findings (convenience count).",
    )

    # ------------------------------------------------------------------
    # Prior-agent linkage
    # ------------------------------------------------------------------
    agent1_output_ref: Optional[str] = Field(
        default=None,
        description="agent1_run_id (if known) linking this run to Agent 1 output.",
    )
    agent2_output_ref: Optional[str] = Field(
        default=None,
        description="agent2_run_id (if known) linking this run to Agent 2 output.",
    )

    # ------------------------------------------------------------------
    # Integrity note
    # ------------------------------------------------------------------
    analysis_note: str = Field(
        default=(
            "Agent 3 performs graph-based network pattern analysis only. "
            "It does NOT produce a final fraud risk score. "
            "All findings are heuristic indicators using prototype thresholds. "
            "They are NOT calibrated fraud probabilities or regulatory determinations. "
            "Missing or incomplete graph data is reported in status and warnings. "
            "An empty findings list with a non-COMPLETE status must NOT be "
            "treated as a confirmed clean network result."
        ),
        description="Documents Agent 3 analysis semantics and limitations.",
    )
