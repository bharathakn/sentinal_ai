"""Tests for the Mock KYC provider."""

from src.evidence.providers.kyc import get_kyc_data
from src.evidence.schemas import EvidenceStatus, SourceMode


class TestKYCKnownAccount:

    def test_known_account_returns_found(self):
        r = get_kyc_data("ACC001")
        assert r.status == EvidenceStatus.FOUND

    def test_source_is_mock(self):
        r = get_kyc_data("ACC001")
        assert r.source_mode == SourceMode.MOCK

    def test_account_id_matches_request(self):
        r = get_kyc_data("ACC001")
        assert r.data.account_id == "ACC001"

    def test_kyc_status_is_verified_for_acc001(self):
        r = get_kyc_data("ACC001")
        assert r.data.kyc_status == "VERIFIED"

    def test_acc001_city_matches_fixture(self):
        r = get_kyc_data("ACC001")
        assert r.data.registered_city == "Bengaluru"

    def test_acc001_not_pep(self):
        r = get_kyc_data("ACC001")
        assert r.data.pep is False

    def test_acc004_is_pep(self):
        r = get_kyc_data("ACC004")
        assert r.data.pep is True

    def test_acc003_kyc_status_pending(self):
        """New account ACC003 should have PENDING KYC."""
        r = get_kyc_data("ACC003")
        assert r.data.kyc_status == "PENDING"

    def test_acc003_location_is_mumbai(self):
        r = get_kyc_data("ACC003")
        assert r.data.registered_city == "Mumbai"

    def test_repeated_calls_return_same_data(self):
        r1 = get_kyc_data("ACC001")
        r2 = get_kyc_data("ACC001")
        assert r1.data.kyc_status == r2.data.kyc_status
        assert r1.data.registered_city == r2.data.registered_city

    def test_synthetic_notice_present(self):
        r = get_kyc_data("ACC001")
        assert "SYNTHETIC" in r.data.synthetic_notice.upper()


class TestKYCUnknownAccount:

    def test_unknown_returns_not_found(self):
        r = get_kyc_data("UNKNOWN")
        assert r.status == EvidenceStatus.NOT_FOUND

    def test_unknown_data_is_none(self):
        r = get_kyc_data("UNKNOWN")
        assert r.data is None

    def test_unknown_has_warning(self):
        r = get_kyc_data("UNKNOWN")
        assert len(r.warnings) > 0
