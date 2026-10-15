"""
Sentinel AI — PaySim Dataset Adapter

Converts a raw row from the PaySim CSV into a CanonicalTransaction.

PaySim schema
-------------
  step            – simulation time unit (1 step = 1 hour)
  type            – transaction type: PAYMENT, TRANSFER, CASH_OUT, CASH_IN, DEBIT
  amount          – transaction amount (USD synthetic)
  nameOrig        – originator account name (e.g. C1231006815, M...)
  oldbalanceOrg   – sender balance before transaction
  newbalanceOrig  – sender balance after transaction
  nameDest        – destination account name
  oldbalanceDest  – receiver balance before transaction
  newbalanceDest  – receiver balance after transaction
  isFraud         – 0/1 label
  isFlaggedFraud  – 0/1 system flag (only triggers for transfers > 200,000)

Notes
-----
- PaySim has no real timestamps; `step` encodes a synthetic simulation hour.
  We store step in metadata. Timestamp is None.
- Merchant accounts start with 'M'; customer accounts start with 'C'.
- Currency is USD (PaySim is calibrated against real Kenyan mobile-money data
  but the amounts are treated as USD for prototype purposes).
- Source: DATASET_REGISTRY.md section 4.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from ..canonical_transaction import (
    AccountInfo,
    CanonicalTransaction,
    DataSource,
    DeviceInfo,
    GeoLocation,
    TransactionChannel,
    TransactionMetadata,
    TransactionStatus,
)


class PaySimAdapter:
    """
    Adapts a single PaySim CSV row dict into a CanonicalTransaction.

    Usage
    -----
    ::

        row = {
            "step": 1,
            "type": "PAYMENT",
            "amount": 9839.64,
            "nameOrig": "C1231006815",
            ...
        }
        canonical = PaySimAdapter.from_row(row)
    """

    _TYPE_TO_CHANNEL: dict[str, TransactionChannel] = {
        "PAYMENT": TransactionChannel.PAYMENT,
        "TRANSFER": TransactionChannel.TRANSFER,
        "CASH_OUT": TransactionChannel.CASH_OUT,
        "CASH_IN": TransactionChannel.CASH_IN,
        "DEBIT": TransactionChannel.DEBIT,
    }

    @classmethod
    def _map_channel(cls, tx_type: Optional[str]) -> TransactionChannel:
        if not tx_type:
            return TransactionChannel.UNKNOWN
        return cls._TYPE_TO_CHANNEL.get(tx_type.upper(), TransactionChannel.UNKNOWN)

    @classmethod
    def _safe_decimal(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        if isinstance(v, float) and v != v:
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    @classmethod
    def _safe_bool(cls, v: Any) -> Optional[bool]:
        if v is None:
            return None
        if isinstance(v, float) and v != v:
            return None
        try:
            return bool(int(v))
        except (ValueError, TypeError):
            return None

    @classmethod
    def _safe_int(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, float) and v != v:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @classmethod
    def from_row(cls, row: dict[str, Any], row_index: Optional[int] = None) -> CanonicalTransaction:
        """
        Convert a raw PaySim row dict into a CanonicalTransaction.

        Parameters
        ----------
        row:
            Dict of column-name → value from the PaySim CSV.
        row_index:
            Optional integer row index used to construct a unique raw_record_id
            when the dataset has no natural transaction key.

        Returns
        -------
        CanonicalTransaction
        """
        # PaySim has no dedicated transaction ID column; we synthesise one.
        name_orig = str(row.get("nameOrig", "UNKNOWN")).strip()
        step = cls._safe_int(row.get("step"))
        idx_part = f"_{row_index}" if row_index is not None else ""
        raw_id = f"PAYSIM_S{step}_{name_orig}{idx_part}"

        amount_raw = row.get("amount", 0)
        amount = Decimal(str(amount_raw)) if amount_raw is not None else Decimal("0")

        tx_type = str(row.get("type", "")).strip().upper() if row.get("type") else None

        # --- Sender ------------------------------------------------------
        balance_before_sender = cls._safe_decimal(row.get("oldbalanceOrg"))
        balance_after_sender = cls._safe_decimal(row.get("newbalanceOrig"))
        sender = AccountInfo(
            account_id=name_orig if name_orig != "UNKNOWN" else None,
            account_name=name_orig if name_orig != "UNKNOWN" else None,
            balance_before=balance_before_sender,
            balance_after=balance_after_sender,
        )

        # --- Receiver ----------------------------------------------------
        name_dest = str(row.get("nameDest", "")).strip()
        balance_before_recv = cls._safe_decimal(row.get("oldbalanceDest"))
        balance_after_recv = cls._safe_decimal(row.get("newbalanceDest"))
        receiver = AccountInfo(
            account_id=name_dest if name_dest else None,
            account_name=name_dest if name_dest else None,
            balance_before=balance_before_recv,
            balance_after=balance_after_recv,
        )

        # --- Metadata ---------------------------------------------------
        metadata = TransactionMetadata(
            paysim_step=step,
            is_flagged_fraud=cls._safe_bool(row.get("isFlaggedFraud")),
            extra={"type": tx_type},
        )

        is_fraud: Optional[bool] = cls._safe_bool(row.get("isFraud"))

        return CanonicalTransaction(
            raw_record_id=raw_id,
            source_dataset=DataSource.PAYSIM,
            amount=amount,
            currency="USD",
            timestamp=None,  # PaySim step is synthetic simulation time, not real datetime
            channel=cls._map_channel(tx_type),
            status=TransactionStatus.UNKNOWN,  # PaySim has no settlement status field
            sender=sender,
            receiver=receiver,
            device=DeviceInfo(),       # PaySim has no device data
            location=GeoLocation(),    # PaySim has no location data
            is_fraud=is_fraud,
            metadata=metadata,
        )
