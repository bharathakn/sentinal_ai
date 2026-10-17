"""Tests for the Mock Device Registry provider."""

from src.evidence.providers.device_registry import check_device
from src.evidence.schemas import EvidenceStatus, SourceMode


class TestDeviceKnownRegistered:

    def test_known_device_registered_to_account(self):
        r = check_device("ACC001", "DEV001")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.is_registered_to_account is True

    def test_registered_device_status_correct(self):
        r = check_device("ACC001", "DEV001")
        assert r.data.registration_status == "REGISTERED"

    def test_first_seen_not_none_for_known_device(self):
        r = check_device("ACC001", "DEV001")
        assert r.data.first_seen is not None

    def test_source_is_mock(self):
        r = check_device("ACC001", "DEV001")
        assert r.source_mode == SourceMode.MOCK


class TestDeviceNewUnregistered:

    def test_new_device_not_registered(self):
        r = check_device("ACC001", "DEV002")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.is_registered_to_account is False

    def test_new_device_has_zero_accounts(self):
        r = check_device("ACC001", "DEV002")
        assert r.data.num_associated_accounts == 0

    def test_new_device_first_seen_none(self):
        r = check_device("ACC001", "DEV002")
        assert r.data.first_seen is None


class TestDeviceShared:

    def test_shared_device_has_multiple_accounts(self):
        r = check_device("ACC001", "DEV003")
        assert r.data.num_associated_accounts == 3

    def test_shared_device_lists_all_accounts(self):
        r = check_device("ACC001", "DEV003")
        for acc in ("ACC001", "ACC003", "ACC004"):
            assert acc in r.data.associated_accounts

    def test_shared_device_registered_to_queried_account(self):
        r = check_device("ACC001", "DEV003")
        assert r.data.is_registered_to_account is True

    def test_shared_device_not_registered_to_acc002(self):
        """DEV003 is shared but ACC002 does not have it."""
        r = check_device("ACC002", "DEV003")
        assert r.data.is_registered_to_account is False


class TestDeviceConsistency:

    def test_repeated_calls_return_same_registration(self):
        r1 = check_device("ACC001", "DEV001")
        r2 = check_device("ACC001", "DEV001")
        assert r1.data.is_registered_to_account == r2.data.is_registered_to_account

    def test_dev001_not_registered_to_acc002(self):
        r = check_device("ACC002", "DEV001")
        assert r.data.is_registered_to_account is False


class TestDeviceUnknown:

    def test_unknown_account_returns_not_found(self):
        r = check_device("UNKNOWN_ACC", "DEV001")
        assert r.status == EvidenceStatus.NOT_FOUND

    def test_unknown_account_data_is_none(self):
        r = check_device("UNKNOWN_ACC", "DEV001")
        assert r.data is None

    def test_completely_unknown_device_returns_not_registered(self):
        r = check_device("ACC001", "DEV_UNKNOWN")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.is_registered_to_account is False
        assert r.data.registration_status == "NOT_REGISTERED"
