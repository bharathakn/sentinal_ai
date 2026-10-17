"""Tests for the Mock Geolocation provider."""

from src.evidence.providers.geolocation import check_geolocation
from src.evidence.schemas import EvidenceStatus, SourceMode

# ACC001 registered: Bengaluru (12.9716, 77.5946)
_ACC001_LAT = 12.9716
_ACC001_LON = 77.5946


class TestGeolocationNormalScenario:

    def test_same_city_is_not_anomalous(self):
        """Transaction in Bengaluru for ACC001 (registered Bengaluru) — not anomalous."""
        r = check_geolocation("ACC001", _ACC001_LAT, _ACC001_LON, "Bengaluru", "India")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.is_anomalous is False

    def test_same_city_distance_near_zero(self):
        r = check_geolocation("ACC001", _ACC001_LAT, _ACC001_LON)
        assert r.data.distance_km is not None
        assert r.data.distance_km < 1.0

    def test_source_is_mock(self):
        r = check_geolocation("ACC001", _ACC001_LAT, _ACC001_LON)
        assert r.source_mode == SourceMode.MOCK


class TestGeolocationSuspiciousScenario:

    def test_distant_location_is_anomalous(self):
        """Transaction from Moscow for ACC001 (registered Bengaluru) — anomalous."""
        r = check_geolocation("ACC001", 55.7558, 37.6176, "Moscow", "Russia")
        assert r.status == EvidenceStatus.FOUND
        assert r.data.is_anomalous is True

    def test_distant_location_distance_exceeds_threshold(self):
        r = check_geolocation("ACC001", 55.7558, 37.6176)
        assert r.data.distance_km is not None
        assert r.data.distance_km >= 500.0

    def test_anomaly_reason_provided_when_flagged(self):
        r = check_geolocation("ACC001", 55.7558, 37.6176)
        assert r.data.anomaly_reason is not None
        assert len(r.data.anomaly_reason) > 0

    def test_transaction_and_registered_location_both_present(self):
        r = check_geolocation("ACC001", 55.7558, 37.6176, "Moscow", "Russia")
        assert r.data.transaction_city == "Moscow"
        assert r.data.registered_city == "Bengaluru"


class TestGeolocationMissingLocation:

    def test_missing_coords_is_anomalous_none_not_false(self):
        """Missing coordinates must produce is_anomalous=None, not False."""
        r = check_geolocation("ACC001", None, None)
        assert r.data.is_anomalous is None

    def test_missing_coords_distance_is_none(self):
        r = check_geolocation("ACC001", None, None)
        assert r.data.distance_km is None

    def test_missing_coords_has_warning(self):
        r = check_geolocation("ACC001", None, None)
        assert len(r.warnings) > 0

    def test_missing_coords_location_data_available_false(self):
        r = check_geolocation("ACC001", None, None)
        assert r.data.location_data_available is False


class TestGeolocationRegisteredLocationPreserved:

    def test_registered_location_present(self):
        r = check_geolocation("ACC001", _ACC001_LAT, _ACC001_LON)
        assert r.data.registered_latitude == _ACC001_LAT
        assert r.data.registered_longitude == _ACC001_LON

    def test_repeated_calls_produce_same_result(self):
        r1 = check_geolocation("ACC001", 55.7558, 37.6176)
        r2 = check_geolocation("ACC001", 55.7558, 37.6176)
        assert r1.data.is_anomalous == r2.data.is_anomalous
        assert r1.data.distance_km == r2.data.distance_km


class TestGeolocationUnknownAccount:

    def test_unknown_account_returns_not_found(self):
        r = check_geolocation("UNKNOWN", 12.9, 77.5)
        assert r.status == EvidenceStatus.NOT_FOUND

    def test_unknown_account_data_is_none(self):
        r = check_geolocation("UNKNOWN", 12.9, 77.5)
        assert r.data is None
