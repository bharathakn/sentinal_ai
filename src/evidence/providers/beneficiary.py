"""Sentinel AI — Mock Beneficiary provider."""

from __future__ import annotations

from datetime import datetime, timezone

from ..fixture_data import (
    get_account,
    get_transaction_history,
    SYNTHETIC_DATA_NOTICE,
)
from ..schemas import (
    BeneficiaryData,
    BeneficiaryResponse,
    EvidenceStatus,
    SourceMode,
)

_SOURCE = "MOCK_BENEFICIARY"

# Accounts known to have a previous fraud flag in the synthetic fixture.
_FRAUD_FLAGGED_ACCOUNTS = {"ACC004"}


def get_beneficiary(account_id: str) -> BeneficiaryResponse:
    """Return the synthetic beneficiary profile for the given account ID."""
    account = get_account(account_id)
    if account is None:
        return BeneficiaryResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=account_id,
            warnings=[f"Beneficiary account '{account_id}' not found in mock fixture."],
        )

    opening_date: datetime | None = account.get("account_opening_date")
    age_days: int | None = None
    if opening_date is not None:
        now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)  # Fixed reference
        delta = now - opening_date
        age_days = max(0, delta.days)

    tx_history = get_transaction_history(account_id)
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
        previous_fraud_flag=account_id in _FRAUD_FLAGGED_ACCOUNTS,
        linked_accounts=linked,
        synthetic_notice=SYNTHETIC_DATA_NOTICE,
    )

    return BeneficiaryResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=account_id,
        data=data,
    )
