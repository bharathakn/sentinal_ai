"""Sentinel AI — Mock KYC provider."""

from __future__ import annotations

from ..fixture_data import get_account, SYNTHETIC_DATA_NOTICE
from ..schemas import (
    EvidenceStatus,
    KYCData,
    KYCResponse,
    SourceMode,
)

_SOURCE = "MOCK_KYC"


def get_kyc_data(account_id: str) -> KYCResponse:
    """Return synthetic KYC customer profile for the requested account."""
    account = get_account(account_id)
    if account is None:
        return KYCResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=account_id,
            warnings=[f"Account '{account_id}' not found in mock KYC fixture."],
        )

    data = KYCData(
        account_id=account_id,
        customer_id=account.get("customer_id"),
        customer_name=account.get("customer_name"),
        kyc_status=account["kyc_status"],
        pep=account.get("pep"),
        account_type=account.get("account_type"),
        account_opening_date=account.get("account_opening_date"),
        occupation=account.get("occupation"),
        income_band=account.get("income_band"),
        registered_city=account.get("registered_city"),
        registered_state=account.get("registered_state"),
        registered_country=account.get("registered_country"),
        synthetic_notice=SYNTHETIC_DATA_NOTICE,
    )

    return KYCResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=account_id,
        data=data,
    )
