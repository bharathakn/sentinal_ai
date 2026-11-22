"""Agent 3 never persists, and examines every cycle up to a safety bound (offline)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.agents.agent3 import Agent3Config, Agent3Status, NetworkAnalyserAgent
from src.agents.agent3 import network_analyser as na
from src.schemas.canonical_transaction import (
    AccountInfo, CanonicalTransaction, DataSource, TransactionChannel, TransactionStatus,
)


def tx():
    return CanonicalTransaction(
        raw_record_id="T1", source_dataset=DataSource.INDIA_SYNTHETIC, amount=Decimal("500"), currency="INR",
        timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc), channel=TransactionChannel.UPI,
        status=TransactionStatus.SUCCESS, sender=AccountInfo(account_id="A"), receiver=AccountInfo(account_id="B"))


@pytest.fixture()
def graph():
    mgr, session, pending = MagicMock(), MagicMock(), MagicMock()
    mgr.session.return_value.__enter__.return_value = session
    session.begin_transaction.return_value = pending
    pending.run.return_value.single.return_value = {"count": 1}
    pending.run.return_value.data.return_value = []
    return mgr, session, pending


def agent(mgr):
    return NetworkAnalyserAgent(config=Agent3Config(), connection_manager=mgr)


def test_subject_is_rolled_back_and_never_committed(graph):
    mgr, session, pending = graph
    assert agent(mgr).analyse(tx()).graph_ingestion_performed
    pending.rollback.assert_called_once()
    pending.commit.assert_not_called()
    session.execute_write.assert_not_called()
    session.run.assert_not_called()  # an autocommit write would persist
    session.close.assert_called_once()


def test_rolled_back_even_when_analysis_crashes(graph, monkeypatch):
    mgr, _, pending = graph
    a = agent(mgr)

    def crash(*args, **kwargs):
        raise RuntimeError("detector crashed")

    monkeypatch.setattr(a, "_analyse_graph", crash)
    with pytest.raises(RuntimeError):
        a._run_with_manager(mgr, transaction=tx(), sender_id="A", receiver_id="B",
                            agent1_output=None, agent2_output=None)
    pending.rollback.assert_called_once()
    pending.commit.assert_not_called()


def test_staging_failure_reads_without_writing(graph):
    mgr, session, pending = graph
    session.begin_transaction.side_effect = RuntimeError("no write access")
    session.run = pending.run
    out = agent(mgr).analyse(tx())
    assert out.graph_ingestion_performed is False
    assert any("could not be staged" in w for w in out.warnings)
    session.execute_write.assert_not_called()


def test_cycle_query_is_not_capped_at_fifty():
    assert na.MAX_CYCLES >= 5000
    assert f"LIMIT {na.MAX_CYCLES}" in na._CYCLES and "LIMIT 50\n" not in na._CYCLES


def test_reaching_the_bound_is_reported_as_partial(graph, monkeypatch):
    mgr, _, _ = graph
    monkeypatch.setattr(na, "MAX_CYCLES", 2)
    a = agent(mgr)
    monkeypatch.setattr(a, "_fetch_cycles", lambda *args, **kw: [{"node_ids": [], "transfers": []}] * 2)
    out = a.analyse(tx())
    assert out.status == Agent3Status.PARTIAL
    assert any("limit" in w for w in out.warnings)
