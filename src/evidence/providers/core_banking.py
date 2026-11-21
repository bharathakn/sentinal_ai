"""
Sentinel AI — Mock Core Banking provider.

Returns synthetic transaction history and account statistics for test accounts.
All data comes from the active evidence data store (src/evidence/data_store.py).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from datetime import datetime

from ..data_store import get_store
from ..schemas import (
    AccountStats,
    CoreBankingData,
    CoreBankingResponse,
    EvidenceStatus,
    SourceMode,
    TransactionRecord,
)


_SOURCE_SUFFIX = "CORE_BANKING"


def get_account_history(account_id: str, as_of: Optional[datetime] = None) -> CoreBankingResponse:
    """Return synthetic transaction history for the requested account.

    Parameters
    ----------
    account_id : str
        The account identifier to look up.

    Returns
    -------
    CoreBankingResponse
        status=FOUND when account is known; NOT_FOUND otherwise.

    as_of : optional; history and stats only include transactions strictly
        before this time (point-in-time evidence). Ignored by the fixture store.
    """
    store = get_store()
    _SOURCE = f"{store.source_prefix}_{_SOURCE_SUFFIX}"
    account = store.get_account(account_id)
    if account is None:
        return CoreBankingResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=account_id,
            warnings=[f"Account '{account_id}' not found in core banking records."],
        )

    raw_history = store.get_transaction_history(account_id, as_of)
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

    raw_stats = store.get_account_stats(account_id, as_of)
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
        synthetic_notice=store.synthetic_notice,
    )

    return CoreBankingResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=account_id,
        data=data,
    )
