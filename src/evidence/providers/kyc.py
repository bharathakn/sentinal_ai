"""Sentinel AI — Mock KYC provider."""

from __future__ import annotations

from ..data_store import get_store
from ..schemas import (
    EvidenceStatus,
    KYCData,
    KYCResponse,
    SourceMode,
)

_SOURCE_SUFFIX = "KYC"


def get_kyc_data(account_id: str) -> KYCResponse:
    """Return synthetic KYC customer profile for the requested account."""
    store = get_store()
    _SOURCE = f"{store.source_prefix}_{_SOURCE_SUFFIX}"
    account = store.get_account(account_id)
    if account is None:
        return KYCResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=account_id,
            warnings=[f"Account '{account_id}' not found in KYC records."],
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
        synthetic_notice=store.synthetic_notice,
    )

    return KYCResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=account_id,
        data=data,
    )
