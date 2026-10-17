"""Tests for the Mock Sanctions provider."""

from src.evidence.providers.sanctions import screen_account, screen_subject
from src.evidence.schemas import EvidenceStatus, SourceMode


class TestSanctionsSubjectScreening:

    def test_known_match_returns_match_found(self):
        r = screen_subject("Synthetic Fraudster One")
        assert r.status == EvidenceStatus.MATCH_FOUND

    def test_known_match_by_key(self):
        r = screen_subject("SANC001")
        assert r.status == EvidenceStatus.MATCH_FOUND

    def test_match_data_is_not_none(self):
        r = screen_subject("Synthetic Fraudster One")
        assert r.data is not None
        assert r.data.matched is True

    def test_match_has_list_name(self):
        r = screen_subject("Synthetic Fraudster One")
        assert r.data.list_name is not None

    def test_clean_subject_returns_no_match(self):
        r = screen_subject("SANC002")
        assert r.status == EvidenceStatus.NO_MATCH

    def test_clean_subject_matched_is_false(self):
        r = screen_subject("SANC002")
        assert r.data.matched is False

    def test_unknown_subject_returns_no_match(self):
        r = screen_subject("Random Person Not In Fixture")
        assert r.status == EvidenceStatus.NO_MATCH

    def test_source_is_mock_for_match(self):
        r = screen_subject("Synthetic Fraudster One")
        assert r.source_mode == SourceMode.MOCK

    def test_source_is_mock_for_no_match(self):
        r = screen_subject("SANC002")
        assert r.source_mode == SourceMode.MOCK

    def test_screening_disclaimer_present_in_match(self):
        r = screen_subject("Synthetic Fraudster One")
        disclaimer = r.data.screening_disclaimer.upper()
        assert "MOCK" in disclaimer or "SYNTHETIC" in disclaimer

    def test_screening_disclaimer_present_in_no_match(self):
        r = screen_subject("SANC002")
        disclaimer = r.data.screening_disclaimer.upper()
        assert "MOCK" in disclaimer or "SYNTHETIC" in disclaimer

    def test_no_claim_of_real_ofac_check(self):
        """Result must not claim to have positively verified a real database.
        The disclaimer must assert that NO real database was consulted."""
        r = screen_subject("Synthetic Fraudster One")
        disclaimer = r.data.screening_disclaimer.upper()
        # The disclaimer must say "NO REAL SANCTIONS DATABASE" — i.e. negate real checks
        assert "NO REAL SANCTIONS DATABASE" in disclaimer or "NOT" in disclaimer
        # Must not claim "OFAC WAS CHECKED" or similar affirmative real-check claim
        assert "OFAC WAS CHECKED" not in disclaimer
        assert "REAL SCREENING COMPLETE" not in disclaimer

    def test_repeated_screening_is_deterministic(self):
        r1 = screen_subject("Synthetic Fraudster One")
        r2 = screen_subject("Synthetic Fraudster One")
        assert r1.data.matched == r2.data.matched
        assert r1.data.list_name == r2.data.list_name


class TestSanctionsAccountScreening:

    def test_acc004_is_flagged(self):
        r = screen_account("ACC004")
        assert r.status == EvidenceStatus.MATCH_FOUND
        assert r.data.matched is True

    def test_acc001_is_clean(self):
        r = screen_account("ACC001")
        assert r.status == EvidenceStatus.NO_MATCH
        assert r.data.matched is False

    def test_acc002_is_clean(self):
        r = screen_account("ACC002")
        assert r.status == EvidenceStatus.NO_MATCH

    def test_acc003_is_clean(self):
        r = screen_account("ACC003")
        assert r.status == EvidenceStatus.NO_MATCH

    def test_unknown_account_returns_no_match(self):
        r = screen_account("UNKNOWN_ACC")
        assert r.status == EvidenceStatus.NO_MATCH

    def test_unknown_account_has_warning(self):
        r = screen_account("UNKNOWN_ACC")
        assert len(r.warnings) > 0
