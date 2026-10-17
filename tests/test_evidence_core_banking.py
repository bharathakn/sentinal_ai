"""Tests for the Mock Core Banking provider."""

from __future__ import annotations

import pytest

from src.evidence.providers.core_banking import get_account_history
from src.evidence.schemas import EvidenceStatus, SourceMode


class TestCoreBankingKnownAccount:

    def test_known_account_returns_found(self):
        r = get_account_history("ACC001")
        assert r.status == EvidenceStatus.FOUND

    def test_source_is_mock(self):
        r = get_account_history("ACC001")
        assert r.source_mode == SourceMode.MOCK
        assert "MOCK" in r.source

    def test_data_not_none_on_found(self):
        r = get_account_history("ACC001")
        assert r.data is not None

    def test_account_id_preserved(self):
        r = get_account_history("ACC001")
        assert r.data.account_id == "ACC001"

    def test_transaction_history_non_empty(self):
        r = get_account_history("ACC001")
        assert len(r.data.transaction_history) > 0

    def test_repeated_calls_return_identical_data(self):
        r1 = get_account_history("ACC001")
        r2 = get_account_history("ACC001")
        assert len(r1.data.transaction_history) == len(r2.data.transaction_history)
        for t1, t2 in zip(r1.data.transaction_history, r2.data.transaction_history):
            assert t1.tx_id == t2.tx_id
            assert t1.amount_inr == t2.amount_inr

    def test_stats_present(self):
        r = get_account_history("ACC001")
        assert r.data.stats is not None

    def test_stats_agree_with_history(self):
        """num_transactions_30d must equal the length of the fixture history."""
        r = get_account_history("ACC001")
        assert r.data.stats.num_transactions_30d == len(r.data.transaction_history)

    def test_avg_debit_agrees_with_fixture(self):
        """avg_debit_amount_inr must agree with actual debit transactions."""
        r = get_account_history("ACC001")
        debits = [t for t in r.data.transaction_history if t.direction == "DEBIT"]
        assert len(debits) > 0
        computed_avg = sum(t.amount_inr for t in debits) / len(debits)
        assert abs(r.data.stats.avg_debit_amount_inr - computed_avg) < 1.0

    def test_transaction_fields_have_correct_types(self):
        r = get_account_history("ACC001")
        for tx in r.data.transaction_history:
            assert isinstance(tx.tx_id, str)
            assert isinstance(tx.amount_inr, float)
            assert tx.direction in ("DEBIT", "CREDIT")

    def test_requested_entity_id_set(self):
        r = get_account_history("ACC001")
        assert r.requested_entity_id == "ACC001"

    def test_acc001_knows_acc002_as_beneficiary(self):
        r = get_account_history("ACC001")
        assert "ACC002" in r.data.stats.known_beneficiaries

    def test_synthetic_notice_in_data(self):
        r = get_account_history("ACC001")
        assert r.data.synthetic_notice is not None
        assert "SYNTHETIC" in r.data.synthetic_notice.upper()


class TestCoreBankingNewAccount:

    def test_acc003_has_limited_history(self):
        r = get_account_history("ACC003")
        assert r.status == EvidenceStatus.FOUND
        assert len(r.data.transaction_history) <= 2

    def test_acc003_no_debits(self):
        r = get_account_history("ACC003")
        debits = [t for t in r.data.transaction_history if t.direction == "DEBIT"]
        assert len(debits) == 0


class TestCoreBankingUnknownAccount:

    def test_unknown_account_returns_not_found(self):
        r = get_account_history("UNKNOWN_ACCT")
        assert r.status == EvidenceStatus.NOT_FOUND

    def test_unknown_account_data_is_none(self):
        r = get_account_history("UNKNOWN_ACCT")
        assert r.data is None

    def test_unknown_account_has_warning(self):
        r = get_account_history("UNKNOWN_ACCT")
        assert len(r.warnings) > 0

    def test_unknown_account_is_mock(self):
        r = get_account_history("UNKNOWN_ACCT")
        assert r.source_mode == SourceMode.MOCK
