"""Sentinel AI — Mock Beneficiary provider."""

from __future__ import annotations

from datetime import datetime

from typing import Optional

from ..data_store import get_store
from ..schemas import (
    BeneficiaryData,
    BeneficiaryResponse,
    EvidenceStatus,
    SourceMode,
)

_SOURCE_SUFFIX = "BENEFICIARY"



def get_beneficiary(account_id: str, as_of: Optional[datetime] = None) -> BeneficiaryResponse:
    """Return the synthetic beneficiary profile for the given account ID.

    as_of : optional; transaction counts / linked accounts use only history
        strictly before this time, and account age is measured at this time.
    """
    store = get_store()
    _SOURCE = f"{store.source_prefix}_{_SOURCE_SUFFIX}"
    account = store.get_account(account_id)
    if account is None:
        return BeneficiaryResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=account_id,
            warnings=[f"Beneficiary account '{account_id}' not found in beneficiary records."],
        )

    opening_date: datetime | None = account.get("account_opening_date")
    age_days: int | None = None
    if opening_date is not None:
        now = store.reference_time(as_of)
        delta = now - opening_date
        age_days = max(0, delta.days)

    tx_history = store.get_transaction_history(account_id, as_of)
    fraud_flag = store.is_fraud_flagged(account_id)
    warnings: list[str] = []
    if fraud_flag is None:
        warnings.append(
            "No fraud-flag registry is available for this data source; "
            "previous_fraud_flag=False means 'not determinable', not 'confirmed clean'."
        )
    known_tx_count = len(tx_history)

    # Linked accounts: counterparties seen in transaction history
    linked = list({tx["counterparty_id"] for tx in tx_history if tx["counterparty_id"]})

    data = BeneficiaryData(
        account_id=account_id,
        customer_name=account.get("customer_name"),
        account_opening_date=opening_date,
        account_age_days=age_days,
        kyc_status=account.get("kyc_status"),
        bank_name=account.get("bank_name"),
        known_transaction_count=known_tx_count,
        previous_fraud_flag=bool(fraud_flag),
        linked_accounts=linked,
        synthetic_notice=store.synthetic_notice,
    )

    return BeneficiaryResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=account_id,
        data=data,
        warnings=warnings,
    )
