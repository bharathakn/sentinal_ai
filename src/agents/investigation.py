"""
Sentinel AI — Sequential investigation runner (Phase 9.5).

Runs the implemented agents in the documented order on one transaction:

    new_case_state (case id + label firewall)
      → Agent 1 Anomaly Detector
      → Agent 2 Evidence Gatherer
      → Agent 3 Network Analyser
      → Agent 4 Risk Assessor
      → Agent 5 Explanation Generator (draft report; optional)

This is a plain sequential runner so the pipeline can be exercised before
LangGraph orchestration (Phase 12). Each agent call follows the same
state-in / state-out contract the LangGraph nodes will use, and agent
instances (models, Neo4j connection) are created once and reused.
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
        if generate_report:
            from .agent5 import ExplanationGeneratorAgent
            self.agent5 = agent5 or ExplanationGeneratorAgent()

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
        from .agent2.evidence_gatherer import gather_evidence

        state: SentinelState = new_case_state(transaction, case_id=case_id)
        tx = state["transaction"]  # label-stripped
        state["agent1_output"] = self.agent1.score(tx)
        state["agent2_output"] = gather_evidence(tx, state["agent1_output"])
        state = self.agent3(state)
        state = self.agent4(state)
        if self.agent5 is not None:
            state = self.agent5(state)
        return state

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
