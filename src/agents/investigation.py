"""
Sentinel AI — Investigation runner.

Runs the investigation on one transaction through the LangGraph pipeline
(Phase 12, ``pipeline_graph.build_investigation_graph``):

    new_case_state (case id + label firewall)
      → Agent 1 Anomaly Detector
      → Agent 2 Evidence Gatherer
      → Agent 3 Network Analyser
      → Agent 4 Risk Assessor
      → Agent 5 Explanation Generator (report; optional)
      → Output Validator (VALIDATED / NEEDS_HUMAN_REVIEW; template fallback)
      → finalise (pipeline_status COMPLETE / DEGRADED / HALTED)

No risk score from Agent 4 → the report is skipped and the case is HALTED
for human review. Agent instances (models, Neo4j connection) and the
compiled graph are created once and reused across cases.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..schemas.canonical_transaction import CanonicalTransaction
from .sentinel_pipeline import SentinelState, new_case_state

logger = logging.getLogger(__name__)


class Investigator:
    """Holds agent instances and runs Agents 1–5 for a transaction.

    ``generate_report=False`` stops after Agent 4 (used by bulk evaluation).
    """

    def __init__(
        self,
        agent1: Any = None,
        agent3: Any = None,
        agent4: Any = None,
        neo4j_manager: Any = None,
        agent5: Any = None,
        generate_report: bool = True,
        validation_stage: Any = None,
        evidence_gatherer: Any = None,
    ) -> None:
        from .agent1 import AnomalyDetectorAgent
        from .agent3 import NetworkAnalyserAgent
        from .agent4 import RiskAssessorAgent

        self._owned_mgr = None
        if agent3 is None and neo4j_manager is None:
            neo4j_manager = self._try_connect()
            self._owned_mgr = neo4j_manager
        self.agent1 = agent1 or AnomalyDetectorAgent()
        self.agent3 = agent3 or NetworkAnalyserAgent(connection_manager=neo4j_manager)
        self.agent4 = agent4 or RiskAssessorAgent()
        self.agent5 = None
        self.validation = None
        if generate_report:
            from .agent5 import ExplanationGeneratorAgent
            from .validator import ValidationStage
            self.agent5 = agent5 or ExplanationGeneratorAgent()
            self.validation = validation_stage or ValidationStage()
        from .pipeline_graph import build_investigation_graph
        self.graph = build_investigation_graph(
            agent1=self.agent1, agent3=self.agent3, agent4=self.agent4,
            agent5=self.agent5, validation_stage=self.validation, evidence_gatherer=evidence_gatherer,
        )

    @staticmethod
    def _try_connect():
        try:
            from ..graph.connection import Neo4jConnectionManager

            mgr = Neo4jConnectionManager()
            mgr.connect()
            mgr.verify_connectivity()
            return mgr
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j unavailable for investigation runner: %s", type(exc).__name__)
            return None  # Agent 3 will report UNAVAILABLE itself

    def investigate(
        self,
        transaction: CanonicalTransaction,
        case_id: Optional[str] = None,
    ) -> SentinelState:
        state: SentinelState = new_case_state(transaction, case_id=case_id)  # label firewall
        return self.graph.invoke(state)

    def close(self) -> None:
        if self._owned_mgr is not None:
            try:
                self._owned_mgr.close()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self) -> "Investigator":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
