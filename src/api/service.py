"""
Sentinel AI — Phase 13: case service.

Creates cases from alerts, runs investigations on a single background worker,
stores the results and records analyst decisions.

* **One worker thread.** Investigations run one at a time, on one
  ``Investigator`` created once per process (models, India store and Neo4j
  connection loaded once). This keeps memory within Render's 512 MB and
  stays within the Groq free-tier rate limit.
* **Restart safety.** On start, cases still ``RECEIVED`` / ``INVESTIGATING``
  (the process stopped mid-investigation) are queued again.
* **Label firewall.** The stored transaction has ground-truth fields removed
  before it is written, whatever the caller sent.
* **Errors.** Only exception *types* are stored, never messages.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Optional

from ..agents.sentinel_pipeline import new_case_id, strip_ground_truth
from ..schemas.canonical_transaction import CanonicalTransaction
from .case_schema import (
    ACTION_PRIORITY, DECIDABLE_STATUSES, UNFINISHED_STATUSES, AlertAccepted, AlertInfo, AlertRequest,
    AlertSource, AnalystAction, AnalystDecision, AuditEvent, AuditEventType, CaseRecord, CaseStatus,
    CaseSummary, DecisionRequest, utcnow,
)
from .case_store import CaseStore

logger = logging.getLogger(__name__)

SYSTEM = "system"
_STATE_EXCLUDE = ("case_id", "case_created_at_utc", "transaction")


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class QueueFull(Exception):
    pass


class FeedUnavailable(Exception):
    pass


# ---------------------------------------------------------------------------
# State → stored investigation
# ---------------------------------------------------------------------------

def _json(v: Any) -> Any:
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    if isinstance(v, list):
        return [_json(x) for x in v]
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def serialise_state(state: dict) -> dict[str, Any]:
    return {k: _json(v) for k, v in state.items() if k not in _STATE_EXCLUDE}


def summary_from_state(state: dict) -> CaseSummary:
    """Copy queue fields from the agents' outputs. Nothing is computed here
    except the queue rank and the human-review flag."""
    a4, a5, v = state.get("agent4_output"), state.get("agent5_output"), state.get("validation_output")
    action = getattr(getattr(a4, "recommended_action", None), "value", None)
    validation = getattr(getattr(v, "status", None), "value", None) if v is not None else None
    if validation is None and a5 is not None:
        validation = a5.validation_status  # validator did not run: NOT_VALIDATED
    pipeline = state.get("pipeline_status")
    return CaseSummary(
        risk_score=getattr(a4, "risk_score", None),
        recommended_action=action,
        score_band_action=getattr(getattr(a4, "score_band_action", None), "value", None),
        confidence=getattr(getattr(a4, "confidence", None), "value", None),
        sar_recommended=getattr(getattr(a4, "sar_recommendation", None), "recommended", None),
        report_generator=getattr(getattr(a5, "generator", None), "value", None),
        validation_status=validation,
        pipeline_status=pipeline,
        requires_human_review=not (validation == "VALIDATED" and pipeline == "COMPLETE"),
        priority_rank=ACTION_PRIORITY.get(action or "", 0),
    )


def _default_investigator():
    from ..agents.investigation import Investigator

    return Investigator()


def _synthetic_feed_lookup(transaction_id: str) -> Optional[dict]:
    from ..evidence.data_store import get_store

    store = get_store()
    if not hasattr(store, "get_transaction"):
        raise FeedUnavailable("The synthetic monitoring feed needs SENTINEL_EVIDENCE_BACKEND=india_synthetic.")
    return store.get_transaction(transaction_id)


# ---------------------------------------------------------------------------

class CaseService:
    def __init__(
        self,
        store: CaseStore,
        investigator_factory: Callable[[], Any] = _default_investigator,
        feed_lookup: Callable[[str], Optional[dict]] = _synthetic_feed_lookup,
        max_pending: int = 50,
    ) -> None:
        self.store = store
        self._factory = investigator_factory
        self._feed_lookup = feed_lookup
        self._max_pending = max_pending
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-investigation")
        self._investigator: Any = None
        self._investigator_error: Optional[str] = None
        self._lock = threading.Lock()
        self._pending = 0

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        """Warm up the investigator and re-queue unfinished cases (worker thread)."""
        self._executor.submit(self._get_investigator)
        try:
            for case_id in self.store.case_ids_with_status(UNFINISHED_STATUSES):
                self.store.update(case_id, {"status": CaseStatus.RECEIVED.value},
                                  events=[AuditEvent(event_type=AuditEventType.INVESTIGATION_REQUEUED, actor=SYSTEM,
                                                     details={"reason": "process restarted before completion"})],
                                  require_status=UNFINISHED_STATUSES)
                self._submit(case_id, force=True)
        except Exception as exc:  # noqa: BLE001 — store down at start: cases stay queued for next start
            logger.warning("Could not re-queue unfinished cases: %s", type(exc).__name__)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self._investigator is not None and hasattr(self._investigator, "close"):
            try:
                self._investigator.close()
            except Exception:  # noqa: BLE001
                pass

    @property
    def pending(self) -> int:
        return self._pending

    @property
    def investigator_ready(self) -> bool:
        return self._investigator is not None

    @property
    def investigator_error(self) -> Optional[str]:
        return self._investigator_error

    def _get_investigator(self) -> Any:
        if self._investigator is None:
            try:
                self._investigator = self._factory()
                self._investigator_error = None
            except Exception as exc:
                self._investigator_error = type(exc).__name__
                logger.error("Investigator could not start: %s", type(exc).__name__)
                raise
        return self._investigator

    def _submit(self, case_id: str, force: bool = False) -> Future:
        with self._lock:
            if not force and self._pending >= self._max_pending:
                raise QueueFull()
            self._pending += 1
        fut = self._executor.submit(self._run, case_id)
        fut.add_done_callback(lambda _: self._done())
        return fut

    def _done(self) -> None:
        with self._lock:
            self._pending -= 1

    # -- ingestion ------------------------------------------------------
    def ingest(self, req: AlertRequest) -> tuple[AlertAccepted, Optional[Future]]:
        if req.transaction is not None:
            tx, source = req.transaction, AlertSource.API
        else:
            row = self._feed_lookup(req.transaction_id)
            if row is None:
                raise NotFound(f"Transaction {req.transaction_id} is not in the synthetic monitoring feed.")
            from ..schemas.adapters.india_adapter import IndiaSyntheticAdapter

            tx, source = IndiaSyntheticAdapter.from_row(row), AlertSource.SYNTHETIC_FEED
        tx = strip_ground_truth(tx)
        key = f"{getattr(tx.source_dataset, 'value', tx.source_dataset)}:{tx.raw_record_id}"

        with self._lock:  # find + create is atomic within this process
            existing = self.store.find_active_by_transaction_key(key)
            if existing is not None:
                return AlertAccepted(case_id=existing.case_id, status=existing.status, duplicate=True,
                                     summary=existing.summary), None
            if self._pending >= self._max_pending:
                raise QueueFull()
            now = utcnow()
            alert = AlertInfo(alert_id=req.alert_id or getattr(tx.metadata, "alert_id", None), source=source,
                              source_system=req.source_system, received_at_utc=now)
            record = CaseRecord(
                case_id=new_case_id(), transaction_key=key, status=CaseStatus.RECEIVED,
                created_at_utc=now, updated_at_utc=now, alert=alert, transaction=tx.model_dump(mode="json"),
                audit_trail=[AuditEvent(event_type=AuditEventType.CASE_CREATED, actor=SYSTEM, at_utc=now,
                                        details={"alert_id": alert.alert_id, "source": source.value,
                                                 "source_system": req.source_system,
                                                 "transaction_id": tx.raw_record_id})],
            )
            self.store.create(record)
        fut = self._submit(record.case_id, force=True)
        return AlertAccepted(case_id=record.case_id, status=record.status, duplicate=False), fut

    # -- investigation (worker thread) -------------------------------
    def _run(self, case_id: str) -> None:
        rec = self.store.update(case_id, {"status": CaseStatus.INVESTIGATING.value},
                                events=[AuditEvent(event_type=AuditEventType.INVESTIGATION_STARTED, actor=SYSTEM)],
                                require_status=UNFINISHED_STATUSES)
        if rec is None:
            return  # already investigated (or not found)
        try:
            tx = CanonicalTransaction.model_validate(rec.transaction)
            state = self._get_investigator().investigate(tx, case_id=case_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Case %s investigation failed: %s", case_id, type(exc).__name__)
            self.store.update(case_id, {"status": CaseStatus.INVESTIGATION_FAILED.value,
                                        "investigation_error": type(exc).__name__},
                              events=[AuditEvent(event_type=AuditEventType.INVESTIGATION_FAILED, actor=SYSTEM,
                                                 details={"error": type(exc).__name__})],
                              require_status=(CaseStatus.INVESTIGATING,))
            return
        summary = summary_from_state(state)
        a5 = state.get("agent5_output")
        self.store.update(
            case_id,
            {"status": CaseStatus.AWAITING_REVIEW.value, "summary": summary,
             "investigation": serialise_state(state), "investigation_error": None},
            events=[AuditEvent(event_type=AuditEventType.INVESTIGATION_COMPLETED, actor=SYSTEM, details={
                "pipeline_status": summary.pipeline_status, "pipeline_version": state.get("pipeline_version"),
                "recommended_action": summary.recommended_action, "risk_score": summary.risk_score,
                "report_run_id": getattr(a5, "agent5_run_id", None), "report_generator": summary.report_generator,
                "validation_status": summary.validation_status, "halt_reason": state.get("halt_reason"),
            })],
            require_status=(CaseStatus.INVESTIGATING,),
        )

    # -- analyst decision ----------------------------------------------
    def decide(self, case_id: str, req: DecisionRequest) -> CaseRecord:
        rec = self.store.get(case_id)
        if rec is None:
            raise NotFound(f"Case {case_id} not found.")
        if rec.status not in DECIDABLE_STATUSES:
            raise Conflict(f"Case {case_id} is {rec.status.value}; a decision needs a completed investigation.")
        s = rec.summary
        report = (rec.investigation or {}).get("agent5_output") or {}
        prev = rec.analyst_decision
        recommended = s.recommended_action
        decision = AnalystDecision(
            analyst_id=req.analyst_id, analyst_name=req.analyst_name, action=req.action, rationale=req.rationale,
            system_recommended_action=recommended, system_risk_score=s.risk_score,
            report_run_id=report.get("agent5_run_id"), report_validation_status=s.validation_status,
            agrees_with_system=(req.action.value == recommended)
            if recommended in {a.value for a in AnalystAction} else None,
            supersedes_decision_id=prev.decision_id if prev else None,
        )
        event = AuditEvent(event_type=AuditEventType.ANALYST_DECISION, actor=req.analyst_id, details={
            "decision_id": decision.decision_id, "action": req.action.value, "analyst_name": req.analyst_name,
            "system_recommended_action": recommended, "system_risk_score": s.risk_score,
            "report_validation_status": s.validation_status,
            "supersedes_decision_id": decision.supersedes_decision_id,
        })
        updated = self.store.update(
            case_id, {"status": CaseStatus.DECIDED.value, "analyst_decision": decision},
            events=[event], decision=decision, require_status=DECIDABLE_STATUSES,
            require_fields={"analyst_decision.decision_id": prev.decision_id} if prev else {"analyst_decision": None},
        )
        if updated is None:
            raise Conflict(f"Case {case_id} changed while the decision was being recorded; reload and retry.")
        return updated

    # -- reads ----------------------------------------------------------
    def get(self, case_id: str) -> CaseRecord:
        rec = self.store.get(case_id)
        if rec is None:
            raise NotFound(f"Case {case_id} not found.")
        return rec


__all__ = ["CaseService", "NotFound", "Conflict", "QueueFull", "FeedUnavailable",
           "summary_from_state", "serialise_state"]
