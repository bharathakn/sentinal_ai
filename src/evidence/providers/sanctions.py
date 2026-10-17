"""
Sentinel AI — Mock Sanctions screening provider.

IMPORTANT: This mock does NOT call any real sanctions database (OFAC, UN,
RBI, or any other). Results are entirely synthetic and are clearly labelled
as such in every response. Do not use this in production.
"""

from __future__ import annotations

from ..fixture_data import (
    get_account_sanctions_result,
    get_sanctions_result,
    SANCTIONS_SUBJECTS,
    SYNTHETIC_DATA_NOTICE,
)
from ..schemas import (
    EvidenceStatus,
    SanctionsData,
    SanctionsResponse,
    SourceMode,
)

_SOURCE = "MOCK_SANCTIONS"

_SCREENING_DISCLAIMER = (
    "MOCK RESULT — No real sanctions database was consulted (OFAC, UN, RBI, or similar). "
    "This is a deterministic synthetic prototype result for testing only. "
    "Do not treat this as a real sanctions screening outcome."
)


def screen_subject(subject_query: str) -> SanctionsResponse:
    """Screen a subject name or identifier against the mock watchlist.

    A deterministic match is returned for 'SANC001' / 'Synthetic Fraudster One'.
    All other queries return no-match.

    Parameters
    ----------
    subject_query : Name or identifier string to screen.

    Returns
    -------
    SanctionsResponse with status MATCH_FOUND or NO_MATCH.
    """
    # Try by key first (SANC001, SANC002...)
    fixture = get_sanctions_result(subject_query)

    # If not found by key, try matching by subject_name in the fixture
    if fixture is None:
        for entry in SANCTIONS_SUBJECTS.values():
            if entry["subject_name"].lower() == subject_query.lower():
                fixture = entry
                break

    if fixture is None:
        # Unknown subject — no match (absence of fixture ≠ confirmed clean)
        data = SanctionsData(
            subject_query=subject_query,
            matched=False,
            match_detail="Subject not found in synthetic mock watchlist.",
            matching_method="EXACT_NAME",
            screening_disclaimer=_SCREENING_DISCLAIMER,
            synthetic_notice=SYNTHETIC_DATA_NOTICE,
        )
        return SanctionsResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NO_MATCH,
            requested_entity_id=subject_query,
            data=data,
            warnings=["Subject not in mock fixture. Absence of match is not a confirmation of clean status."],
        )

    status = EvidenceStatus.MATCH_FOUND if fixture["matched"] else EvidenceStatus.NO_MATCH
    data = SanctionsData(
        subject_query=subject_query,
        matched=fixture["matched"],
        list_name=fixture.get("list_name"),
        match_detail=fixture.get("match_detail"),
        match_confidence=fixture.get("match_confidence"),
        matching_method=fixture.get("matching_method"),
        list_date=fixture.get("list_date"),
        screening_disclaimer=_SCREENING_DISCLAIMER,
        synthetic_notice=fixture.get("synthetic_notice", SYNTHETIC_DATA_NOTICE),
    )

    return SanctionsResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=status,
        requested_entity_id=subject_query,
        data=data,
    )


def screen_account(account_id: str) -> SanctionsResponse:
    """Screen an account ID by mapping it to its synthetic sanctions subject.

    Convenience wrapper for account-based screening in the investigation pipeline.
    """
    fixture = get_account_sanctions_result(account_id)
    if fixture is None:
        # Account not in fixture — no match, with a note
        data = SanctionsData(
            subject_query=account_id,
            matched=False,
            match_detail="Account not found in mock fixture mapping.",
            matching_method="ACCOUNT_LOOKUP",
            screening_disclaimer=_SCREENING_DISCLAIMER,
            synthetic_notice=SYNTHETIC_DATA_NOTICE,
        )
        return SanctionsResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NO_MATCH,
            requested_entity_id=account_id,
            data=data,
            warnings=[f"Account '{account_id}' not in mock sanctions mapping."],
        )

    status = EvidenceStatus.MATCH_FOUND if fixture["matched"] else EvidenceStatus.NO_MATCH
    data = SanctionsData(
        subject_query=account_id,
        matched=fixture["matched"],
        list_name=fixture.get("list_name"),
        match_detail=fixture.get("match_detail"),
        match_confidence=fixture.get("match_confidence"),
        matching_method=fixture.get("matching_method"),
        list_date=fixture.get("list_date"),
        screening_disclaimer=_SCREENING_DISCLAIMER,
        synthetic_notice=fixture.get("synthetic_notice", SYNTHETIC_DATA_NOTICE),
    )

    return SanctionsResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=status,
        requested_entity_id=account_id,
        data=data,
    )
