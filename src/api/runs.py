"""
Sentinel AI — dataset investigation runs.

    dataset → Agent 1 screens every transaction
            → N of the flagged go through the full five-agent graph + validator
              (uploads: the strongest; demo: the strongest of each suspected pattern)
            → each becomes a normal case, resolved by an analyst decision

Progress is an append-only event log the dashboard polls. Events are emitted
by the agents as they run, not simulated.

Isolation for uploads: an in-memory graph of that file only, an evidence
store with no bank records, and no LLM unless the analyst opted in. An
uploaded dataset never reads or writes the shared Neo4j graph.
"""

from __future__ import annotations

import heapq
import logging
import threading
from collections import Counter
from contextlib import nullcontext
from typing import Any, Callable, Optional
from uuid import uuid4

from ..agents.pipeline_graph import observe
from ..agents.sentinel_pipeline import new_case_id, strip_ground_truth
from ..evidence.data_store import UploadedDatasetStore, use_store
from .case_schema import (
    AlertInfo, AlertSource, AuditEvent, AuditEventType, CaseRecord, CaseStatus, utcnow,
)
from .case_store import _now_json
from .datasets import Dataset
from .limits import DailyAllowance
from .demo_selection import pick_varied
from .run_events import node_view
from .run_store import RunStore
from .service import CaseService, NotFound, QueueFull

logger = logging.getLogger(__name__)

QUEUED, SCREENING, INVESTIGATING, COMPLETED, FAILED = "QUEUED", "SCREENING", "INVESTIGATING", "COMPLETED", "FAILED"
ACTIVE = (QUEUED, SCREENING, INVESTIGATING)
CHUNK = 500
BINS = 24
MAX_INVESTIGATE = 10
MAX_ACTIVE_RUNS = 3  # each holds a dataset in memory until it finishes
LOAD_WAIT_SECONDS = 20


class RunService:
    def __init__(self, cases: CaseService, store: RunStore, allowance: Optional[DailyAllowance] = None) -> None:
        self.cases = cases
        self.store = store
        self.allowance = allowance or DailyAllowance()
        self._loading = threading.Lock()  # one dataset is parsed at a time
        self._active_by: Counter = Counter()
        self._lock = threading.Lock()
        self._active = 0
        self._seq: dict[str, int] = {}

    def start(self) -> None:
        try:
            for run_id in self.store.ids_with_status(ACTIVE):
                self.store.update(run_id, {"status": FAILED, "error": "InterruptedByRestart",
                                           "completed_at_utc": _now_json()})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not close interrupted runs: %s", type(exc).__name__)

    # -- reads ----------------------------------------------------------
    def get(self, run_id: str, workspace: Optional[str] = None) -> dict:
        run = self.store.get(run_id)
        if run is None or (workspace is not None and run.get("created_by") != workspace):
            raise NotFound(f"Run {run_id} not found.")
        return run

    def events(self, run_id: str, after: int = 0, workspace: Optional[str] = None) -> dict:
        status = self.get(run_id, workspace)["status"]  # read first: a terminal status implies every event is written
        events = self.store.events(run_id, after=after, limit=500)
        return {"status": status, "events": events, "next": events[-1]["seq"] if events else after,
                "more": len(events) == 500}

    # -- create ---------------------------------------------------------
    def check_capacity(self, workspace: Optional[str]) -> None:
        """Cheap check, made before a dataset is read into memory."""
        if self._active >= MAX_ACTIVE_RUNS or (workspace is not None and self._active_by[workspace] >= 1):
            raise QueueFull()
        self.allowance.check(workspace)

    def launch(self, load: Callable[[], Dataset], created_by: str, workspace: Optional[str],
               investigate_top: int, llm_reports: bool) -> dict:
        self.check_capacity(workspace)
        if not self._loading.acquire(timeout=LOAD_WAIT_SECONDS):
            raise QueueFull()
        try:
            self.check_capacity(workspace)
            run = self.create(load(), created_by, investigate_top, llm_reports)
        finally:
            self._loading.release()
        self.allowance.spend(workspace)
        return run

    def create(self, dataset: Dataset, created_by: str, investigate_top: int, llm_reports: bool) -> dict:
        with self._lock:
            if self._active >= MAX_ACTIVE_RUNS:
                raise QueueFull()
            self._active += 1
            self._active_by[created_by] += 1
        try:
            run_id = f"RUN-{uuid4().hex[:12].upper()}"
            run = {
                "run_id": run_id, "status": QUEUED, "created_by": created_by, "created_at_utc": _now_json(),
                "completed_at_utc": None, "dataset": dataset.info(), "error": None,
                "settings": {"investigate_top": max(1, min(MAX_INVESTIGATE, investigate_top)),
                             "llm_reports": bool(llm_reports)},
                "screening": None, "cases": [], "result": None,
            }
            self.store.create(run)
            self._emit(run_id, "run.queued", {"dataset": run["dataset"], "settings": run["settings"]})
            self.cases.submit_job(lambda: self._execute(run, dataset, created_by))
        except Exception:
            self._release(created_by)
            raise
        return run

    def _release(self, created_by: str) -> None:
        with self._lock:
            self._active -= 1
            self._active_by[created_by] -= 1
            if self._active_by[created_by] <= 0:
                del self._active_by[created_by]

    def _emit(self, run_id: str, kind: str, data: dict, case_id: Optional[str] = None) -> None:
        seq = self._seq[run_id] = self._seq.get(run_id, 0) + 1
        self.store.append_event(run_id, {"seq": seq, "at_utc": _now_json(), "type": kind,
                                         "case_id": case_id, "data": data})

    # -- worker thread --------------------------------------------------
    def _execute(self, run: dict, dataset: Dataset, created_by: str) -> None:
        run_id = run["run_id"]
        try:
            self.store.update(run_id, {"status": SCREENING})
            self._emit(run_id, "run.started", {"dataset": run["dataset"]})
            shared = self.cases.investigator()
            screening, selected = self._screen(run, dataset, shared.agent1)
            self.store.update(run_id, {"status": INVESTIGATING, "screening": screening})

            investigator = self._investigator_for(run, dataset, shared) if selected else shared
            scope = (lambda: use_store(UploadedDatasetStore())) if dataset.kind == "UPLOAD" else nullcontext
            results: list[dict] = []
            with scope():
                for rank, (hit, row) in enumerate(selected, start=1):
                    results.append(self._investigate(run, dataset, row, hit, rank, created_by, investigator))
                    self.store.update(run_id, {"cases": results})

            result = {
                "screened": screening["screened"], "flagged": screening["flagged"], "investigated": len(results),
                "not_investigated": screening["flagged"] - len(results),
                "by_action": dict(Counter(r["summary"]["recommended_action"] or "NONE" for r in results)),
                "validated": sum(r["summary"]["validation_status"] == "VALIDATED" for r in results),
                "sar_recommended": sum(bool(r["summary"]["sar_recommended"]) for r in results),
                "failed": sum(r["status"] == CaseStatus.INVESTIGATION_FAILED.value for r in results),
            }
            self._emit(run_id, "run.completed", {"result": result})
            self.store.update(run_id, {"status": COMPLETED, "result": result, "completed_at_utc": _now_json()})
        except Exception as exc:  # noqa: BLE001 — only the type is stored
            logger.error("Run %s failed: %s", run_id, type(exc).__name__)
            try:
                self._emit(run_id, "run.failed", {"error": type(exc).__name__})
                self.store.update(run_id, {"status": FAILED, "error": type(exc).__name__,
                                           "completed_at_utc": _now_json()})
            except Exception as store_exc:  # noqa: BLE001
                logger.error("Run %s failure could not be stored: %s", run_id, type(store_exc).__name__)
        finally:
            self._release(created_by)
            self._seq.pop(run_id, None)

    def _screen(self, run: dict, dataset: Dataset, agent1: Any) -> tuple[dict, list[tuple[dict, dict]]]:
        run_id, top_n = run["run_id"], run["settings"]["investigate_top"]
        total = len(dataset.rows)
        thresholds = agent1.screening_thresholds
        self._emit(run_id, "screening.started", {"total": total, "thresholds": thresholds})
        bins, flagged_bins = [0] * BINS, [0] * BINS
        flagged, hits = 0, []
        for start in range(0, total, CHUNK):
            rows = dataset.rows[start:start + CHUNK]
            txs = [strip_ground_truth(dataset.transaction(r)) for r in rows]
            results = agent1.screen(txs)
            sample = []
            for offset, (tx, res) in enumerate(zip(txs, results)):
                b = min(BINS - 1, int(res["combined_confidence"] * BINS))
                bins[b] += 1
                brief = {"transaction_id": res["transaction_id"], "amount": str(tx.amount), "currency": tx.currency,
                         "channel": str(getattr(tx.channel, "value", tx.channel)),
                         "sender": tx.sender.account_id, "receiver": tx.receiver.account_id,
                         "combined_confidence": res["combined_confidence"], "flagged": res["flagged"]}
                if res["flagged"]:
                    flagged += 1
                    flagged_bins[b] += 1
                    hits.append((res["combined_confidence"], -(start + offset), brief))
                if offset % max(1, len(txs) // 12) == 0:
                    sample.append(brief)
            self._emit(run_id, "screening.progress", {
                "screened": start + len(rows), "total": total, "flagged": flagged,
                "histogram": list(bins), "flagged_histogram": list(flagged_bins), "sample": sample})
        rule = "strongest"
        if dataset.kind == "DEMO" and top_n > 1:
            rule = "varied"
            by_index = {-h[1]: h[2] for h in hits}
            ranked = [-h[1] for h in sorted(hits, key=lambda h: (h[0], h[1]), reverse=True)]
            picked = [({**by_index[i], "lead": lead}, i)
                      for i, lead in pick_varied(dataset.transactions(), ranked, top_n)]
        else:
            picked = [(h[2], -h[1]) for h in heapq.nlargest(top_n, hits, key=lambda h: (h[0], h[1]))]
        screening = {"screened": total, "flagged": flagged, "thresholds": thresholds, "histogram": bins,
                     "flagged_histogram": flagged_bins, "selection_rule": rule,
                     "selected": [hit for hit, _ in picked]}
        self._emit(run_id, "screening.completed", screening)
        return screening, [(hit, dataset.rows[i]) for hit, i in picked]

    def _investigator_for(self, run: dict, dataset: Dataset, shared: Any) -> Any:
        llm = run["settings"]["llm_reports"]
        if dataset.kind != "UPLOAD" and llm:
            return shared
        from ..agents.agent5 import ExplanationGeneratorAgent
        from ..agents.investigation import Investigator

        agent3 = shared.agent3
        if dataset.kind == "UPLOAD":
            from ..agents.agent3.dataset_graph import DatasetNetworkAnalyserAgent, InMemoryTransferGraph

            agent3 = DatasetNetworkAnalyserAgent(InMemoryTransferGraph(dataset.transactions()))
        agent5 = shared.agent5 if llm else ExplanationGeneratorAgent(llm_client=None)
        return Investigator(agent1=shared.agent1, agent3=agent3, agent4=shared.agent4, agent5=agent5,
                            validation_stage=shared.validation)

    def _investigate(self, run: dict, dataset: Dataset, row: dict, hit: dict, rank: int,
                     created_by: str, investigator: Any) -> dict:
        run_id, now = run["run_id"], utcnow()
        tx = strip_ground_truth(dataset.transaction(row))
        case_id = new_case_id()
        self.cases.store.create(CaseRecord(
            case_id=case_id, owner=created_by, transaction_key=f"{run_id}:{tx.raw_record_id}", status=CaseStatus.RECEIVED,
            created_at_utc=now, updated_at_utc=now, transaction=tx.model_dump(mode="json"),
            alert=AlertInfo(source=AlertSource.DATASET_RUN, source_system=dataset.name[:64],
                            received_at_utc=now, run_id=run_id),
            audit_trail=[AuditEvent(event_type=AuditEventType.CASE_CREATED, actor=created_by, at_utc=now, details={
                "source": AlertSource.DATASET_RUN.value, "run_id": run_id, "rank": rank,
                "transaction_id": tx.raw_record_id, "screening_confidence": hit["combined_confidence"]})],
        ))
        self._emit(run_id, "case.started", {"rank": rank, "transaction": hit,
                                            "timestamp": tx.timestamp.isoformat() if tx.timestamp else None}, case_id)

        def on_node(phase, node, record, state, update) -> None:
            if phase == "started":
                self._emit(run_id, "agent.started", {"node": node.value}, case_id)
                return
            try:
                view = node_view(node, state, update)
            except Exception as exc:  # noqa: BLE001 — the step still has to be reported as finished
                logger.warning("No live view for %s: %s", node.value, type(exc).__name__)
                view = {}
            self._emit(run_id, "agent.completed", {
                "node": node.value, "outcome": record.outcome.value, "error": record.error,
                "duration_ms": record.duration_ms, "view": view}, case_id)

        with observe(on_node):
            self.cases.investigate_case(case_id, investigator)
        rec = self.cases.store.get(case_id)
        result = {"case_id": case_id, "rank": rank, "transaction": hit, "status": rec.status.value,
                  "summary": rec.summary.model_dump(mode="json")}
        self._emit(run_id, "case.completed", result, case_id)
        return result


__all__ = ["RunService"]
