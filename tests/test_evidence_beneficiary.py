"""Tests for the Mock Beneficiary provider."""

from datetime import datetime, timezone

from src.evidence.providers.beneficiary import get_beneficiary
from src.evidence.schemas import EvidenceStatus, SourceMode


class TestBeneficiaryKnown:

    def test_known_beneficiary_returns_found(self):
        r = get_beneficiary("ACC002")
        assert r.status == EvidenceStatus.FOUND

    def test_source_is_mock(self):
        r = get_beneficiary("ACC002")
        assert r.source_mode == SourceMode.MOCK

    def test_account_id_matches(self):
        r = get_beneficiary("ACC002")
        assert r.data.account_id == "ACC002"

    def test_account_age_days_agrees_with_opening_date(self):
        """account_age_days must agree with account_opening_date relative to ref date."""
        r = get_beneficiary("ACC002")
        assert r.data.account_opening_date is not None
        assert r.data.account_age_days is not None
        ref = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        expected_age = (ref - r.data.account_opening_date).days
        assert r.data.account_age_days == expected_age

    def test_acc002_is_not_fraud_flagged(self):
        r = get_beneficiary("ACC002")
        assert r.data.previous_fraud_flag is False

    def test_acc002_transaction_history_non_empty(self):
        r = get_beneficiary("ACC002")
        assert r.data.known_transaction_count > 0

    def test_acc002_linked_to_acc001(self):
        """ACC002 transacts with ACC001, so ACC001 should appear in linked accounts."""
        r = get_beneficiary("ACC002")
        assert "ACC001" in r.data.linked_accounts

    def test_acc003_is_new_account(self):
        """ACC003 is the 'new beneficiary' scenario — age must be very small."""
        r = get_beneficiary("ACC003")
        assert r.data.account_age_days is not None
        assert r.data.account_age_days <= 5

    def test_acc004_is_fraud_flagged(self):
        r = get_beneficiary("ACC004")
        assert r.data.previous_fraud_flag is True

    def test_beneficiary_matches_core_banking_recipient(self):
        """
        The beneficiary returned by get_beneficiary('ACC002') must correspond to
        the same ACC002 that appears as counterparty in ACC001's debit history.
        """
        from src.evidence.providers.core_banking import get_account_history
        banking = get_account_history("ACC001")
        recipients = {
            tx.counterparty_id
            for tx in banking.data.transaction_history
            if tx.direction == "DEBIT"
        }
        assert "ACC002" in recipients

        bene = get_beneficiary("ACC002")
        assert bene.data.account_id == "ACC002"

    def test_repeated_calls_are_consistent(self):
        r1 = get_beneficiary("ACC002")
        r2 = get_beneficiary("ACC002")
        assert r1.data.account_age_days == r2.data.account_age_days
        assert r1.data.known_transaction_count == r2.data.known_transaction_count


class TestBeneficiaryUnknown:

    def test_unknown_returns_not_found(self):
        r = get_beneficiary("UNKNOWN")
        assert r.status == EvidenceStatus.NOT_FOUND

    def test_unknown_data_is_none(self):
        r = get_beneficiary("UNKNOWN")
        assert r.data is None

    def test_unknown_has_warning(self):
        r = get_beneficiary("UNKNOWN")
        assert len(r.warnings) > 0
