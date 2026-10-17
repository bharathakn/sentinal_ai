"""
Sentinel AI — Mock Core Banking provider.

Returns synthetic transaction history and account statistics for test accounts.
All data comes from src/evidence/fixture_data.py (single source of truth).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ..fixture_data import (
    get_account,
    get_account_stats,
    get_transaction_history,
    SYNTHETIC_DATA_NOTICE,
)
from ..schemas import (
    AccountStats,
    CoreBankingData,
    CoreBankingResponse,
    EvidenceStatus,
    SourceMode,
    TransactionRecord,
)


_SOURCE = "MOCK_CORE_BANKING"


def get_account_history(account_id: str) -> CoreBankingResponse:
    """Return synthetic transaction history for the requested account.

    Parameters
    ----------
    account_id : str
        The account identifier to look up.

    Returns
    -------
    CoreBankingResponse
        status=FOUND when account is known; NOT_FOUND otherwise.
    """
    account = get_account(account_id)
    if account is None:
        return CoreBankingResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=account_id,
            warnings=[f"Account '{account_id}' not found in mock core banking fixture."],
        )

    raw_history = get_transaction_history(account_id)
    transaction_records = [
        TransactionRecord(
            tx_id=tx["tx_id"],
            counterparty_id=tx["counterparty_id"],
            amount_inr=float(tx["amount_inr"]),
            direction=tx["direction"],
            channel=tx["channel"],
            timestamp=tx["timestamp"],
            description=tx["description"],
        )
        for tx in raw_history
    ]

    raw_stats = get_account_stats(account_id)
    stats = None
    if raw_stats is not None:
        stats = AccountStats(
            num_transactions_30d=raw_stats["num_transactions_30d"],
            avg_debit_amount_inr=float(raw_stats["avg_debit_amount_inr"]),
            max_debit_30d_inr=float(raw_stats["max_debit_30d_inr"]),
            known_beneficiaries=list(raw_stats["known_beneficiaries"]),
            tx_frequency_per_week=raw_stats["tx_frequency_per_week"],
            computation_note=raw_stats["computation_note"],
        )

    data = CoreBankingData(
        account_id=account_id,
        account_type=account.get("account_type"),
        bank_name=account.get("bank_name"),
        transaction_history=transaction_records,
        stats=stats,
        synthetic_notice=SYNTHETIC_DATA_NOTICE,
    )

    return CoreBankingResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=account_id,
        data=data,
    )
