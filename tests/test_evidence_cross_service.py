"""
Cross-service consistency integration tests.

Verifies that all evidence providers agree on the same shared synthetic
scenarios. No provider should return data that contradicts another.
"""

from __future__ import annotations

import pytest

from src.evidence.providers.core_banking import get_account_history
from src.evidence.providers.kyc import get_kyc_data
from src.evidence.providers.device_registry import check_device
from src.evidence.providers.beneficiary import get_beneficiary
from src.evidence.providers.sanctions import screen_account
from src.evidence.providers.geolocation import check_geolocation
from src.evidence.providers.news.mock_provider import MockNewsProvider
from src.evidence.schemas import EvidenceStatus


class TestNormalScenarioConsistency:
    """
    Normal scenario: ACC001 sends to ACC002 via DEV001 from Bengaluru.
    All providers must agree on this scenario.
    """

    def test_acc001_is_sender_in_core_banking(self):
        r = get_account_history("ACC001")
        assert r.status == EvidenceStatus.FOUND
        debit_counterparties = {
            tx.counterparty_id for tx in r.data.transaction_history
            if tx.direction == "DEBIT"
        }
        assert "ACC002" in debit_counterparties

    def test_kyc_recognizes_acc001(self):
        r = get_kyc_data("ACC001")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.account_id == "ACC001"

    def test_acc001_kyc_location_matches_banking_scenario(self):
        """KYC registered city for ACC001 must be Bengaluru (normal location scenario)."""
        r = get_kyc_data("ACC001")
        assert r.data.registered_city == "Bengaluru"

    def test_device_registry_recognizes_acc001_dev001(self):
        r = check_device("ACC001", "DEV001")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.is_registered_to_account is True

    def test_acc002_is_recipient_in_core_banking(self):
        r = get_account_history("ACC001")
        recipients = {
            tx.counterparty_id for tx in r.data.transaction_history
            if tx.direction == "DEBIT"
        }
        assert "ACC002" in recipients

    def test_beneficiary_recognizes_acc002(self):
        r = get_beneficiary("ACC002")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.account_id == "ACC002"

    def test_acc002_beneficiary_linked_to_acc001(self):
        r = get_beneficiary("ACC002")
        assert "ACC001" in r.data.linked_accounts

    def test_geolocation_normal_for_acc001_in_bengaluru(self):
        r = check_geolocation("ACC001", 12.9716, 77.5946, "Bengaluru", "India")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.is_anomalous is False

    def test_sanctions_acc001_clean(self):
        r = screen_account("ACC001")
        assert r.status == EvidenceStatus.NO_MATCH

    def test_sanctions_acc002_clean(self):
        r = screen_account("ACC002")
        assert r.status == EvidenceStatus.NO_MATCH


class TestSuspiciousScenarioConsistency:
    """
    Suspicious scenario: ACC001 sends large amount to ACC003 (new account).
    All providers must agree on this scenario.
    """

    def test_acc003_appears_in_acc001_debit_history(self):
        r = get_account_history("ACC001")
        recipients = {
            tx.counterparty_id for tx in r.data.transaction_history
            if tx.direction == "DEBIT"
        }
        assert "ACC003" in recipients

    def test_acc003_beneficiary_is_new(self):
        r = get_beneficiary("ACC003")
        assert r.data.account_age_days is not None
        assert r.data.account_age_days <= 5, (
            f"ACC003 should be a new account; got age_days={r.data.account_age_days}"
        )

    def test_acc003_kyc_is_pending(self):
        r = get_kyc_data("ACC003")
        assert r.data.kyc_status == "PENDING"

    def test_dev002_is_new_device(self):
        r = check_device("ACC001", "DEV002")
        assert r.data.is_registered_to_account is False
        assert r.data.num_associated_accounts == 0

    def test_geolocation_flags_moscow_as_suspicious(self):
        r = check_geolocation("ACC001", 55.7558, 37.6176, "Moscow", "Russia")
        assert r.data.is_anomalous is True

    def test_acc004_is_sanctions_matched(self):
        r = screen_account("ACC004")
        assert r.status == EvidenceStatus.MATCH_FOUND


class TestScenarioIsolation:
    """Normal and suspicious scenarios must not contaminate each other."""

    def test_acc001_normal_geo_after_suspicious_geo(self):
        """Suspicious check for ACC001 must not affect subsequent normal check."""
        _suspicious = check_geolocation("ACC001", 55.7558, 37.6176)
        normal = check_geolocation("ACC001", 12.9716, 77.5946)
        assert normal.data.is_anomalous is False

    def test_sanctions_clean_after_match(self):
        _match = screen_account("ACC004")
        clean = screen_account("ACC001")
        assert clean.status == EvidenceStatus.NO_MATCH

    def test_dev001_registered_after_dev002_check(self):
        _new = check_device("ACC001", "DEV002")
        known = check_device("ACC001", "DEV001")
        assert known.data.is_registered_to_account is True

    def test_unknown_account_does_not_affect_known(self):
        _unknown = get_kyc_data("UNKNOWN")
        known = get_kyc_data("ACC001")
        assert known.status == EvidenceStatus.FOUND


class TestIncompleteEvidenceScenario:
    """Missing/incomplete evidence must be clearly indicated."""

    def test_missing_geolocation_is_anomalous_none(self):
        r = check_geolocation("ACC001", None, None)
        assert r.data.is_anomalous is None

    def test_unknown_beneficiary_is_not_found(self):
        r = get_beneficiary("UNKNOWN_BENE")
        assert r.status == EvidenceStatus.NOT_FOUND
        assert r.data is None

    def test_unknown_device_not_registered(self):
        r = check_device("ACC001", "TOTALLY_UNKNOWN_DEV")
        assert r.data.is_registered_to_account is False
        assert r.data.registration_status == "NOT_REGISTERED"

    def test_news_no_articles_is_not_error(self):
        provider = MockNewsProvider()
        r = provider.search("Clean User (SYNTHETIC)")
        assert r.status == EvidenceStatus.NO_ARTICLES
        # Must NOT be a PROVIDER_ERROR — these are distinct states
        assert r.status != EvidenceStatus.PROVIDER_ERROR

    def test_no_articles_warning_about_interpretation(self):
        provider = MockNewsProvider()
        r = provider.search("Clean User (SYNTHETIC)")
        all_warnings = " ".join(r.warnings).lower()
        assert "not" in all_warnings or "does not prove" in all_warnings
