"""
Sentinel AI — India Synthetic Dataset Adapter

Converts merged rows from the India Synthetic dataset:
  - dataset/processed/custom_india/transactions_features.csv
  - dataset/processed/custom_india/transactions_targets.csv

into a CanonicalTransaction.

India Synthetic schema
----------------------
transactions_features.csv columns:
  transaction_id               – primary key (TXN_IND_YYYYMM_NNNNNN)
  timestamp                    – ISO-8601 offset-aware datetime (IST +05:30)
  day_of_month, hour_of_day, day_of_week
  channel                      – UPI / NEFT / RTGS
  transaction_type             – P2P / C2B
  amount_inr                   – INR decimal amount
  status                       – SUCCESS / FAILED / PENDING / REVERSED
  sender_account_id            – ACC_IND_NNNNNN
  receiver_account_id          – ACC_IND_NNNNNN
  sender_customer_id           – CUST_IND_NNNNNN
  receiver_customer_id         – CUST_IND_NNNNNN
  sender_vpa                   – UPI VPA string
  receiver_vpa                 – UPI VPA string
  sender_ifsc                  – IFSC code
  receiver_ifsc                – IFSC code
  device_id                    – DEV_IND_NNNNNN
  ip_address
  tx_city, tx_state
  tx_lat, tx_long
  distance_from_home_km
  is_new_device                – 0/1
  is_new_beneficiary           – 0/1
  time_since_beneficiary_added_min
  amount_ratio_vs_30d_avg
  tx_frequency_24h
  time_since_last_tx_sec
  account_balance_before
  account_balance_after

transactions_targets.csv columns:
  transaction_id               – foreign key
  alert_id
  is_fraud                     – 0/1
  risk_label                   – e.g. "HIGH_RISK"
  is_flagged_alert             – 0/1
  scenario_id                  – SCENARIO_N_NAME

Notes
-----
- Currency is INR (Indian Rupee) throughout.
- This is 100% synthetic data; see DATASET_REGISTRY.md §7 disclaimer.
- Source: DATASET_REGISTRY.md section 7.
"""

from __future__ import annotations

from datetime import datetime
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


class IndiaSyntheticAdapter:
    """
    Adapts a single India Synthetic row (features optionally merged with targets)
    into a CanonicalTransaction.

    Usage
    -----
    ::

        # features-only row
        row = {
            "transaction_id": "TXN_IND_202608_000001",
            "timestamp": "2026-08-09T17:55:21+05:30",
            "channel": "NEFT",
            "amount_inr": 5373.78,
            ...
        }
        canonical = IndiaSyntheticAdapter.from_row(row)

        # merged features + targets row
        merged_row = {**features_row, **targets_row}
        canonical = IndiaSyntheticAdapter.from_row(merged_row)
    """

    _CHANNEL_MAP: dict[str, TransactionChannel] = {
        "UPI": TransactionChannel.UPI,
        "NEFT": TransactionChannel.NEFT,
        "RTGS": TransactionChannel.RTGS,
        "IMPS": TransactionChannel.IMPS,
    }

    _STATUS_MAP: dict[str, TransactionStatus] = {
        "SUCCESS": TransactionStatus.SUCCESS,
        "FAILED": TransactionStatus.FAILED,
        "PENDING": TransactionStatus.PENDING,
        "REVERSED": TransactionStatus.REVERSED,
    }

    @classmethod
    def _map_channel(cls, channel: Optional[str]) -> TransactionChannel:
        if not channel:
            return TransactionChannel.UNKNOWN
        return cls._CHANNEL_MAP.get(channel.upper().strip(), TransactionChannel.UNKNOWN)

    @classmethod
    def _map_status(cls, status: Optional[str]) -> TransactionStatus:
        if not status:
            return TransactionStatus.UNKNOWN
        return cls._STATUS_MAP.get(status.upper().strip(), TransactionStatus.UNKNOWN)

    @classmethod
    def _parse_timestamp(cls, v: Any) -> Optional[datetime]:
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(str(v))
        except (ValueError, TypeError):
            return None

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
    def _safe_float(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, float) and v != v:
            return None
        try:
            return float(v)
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
    def _safe_str(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, float) and v != v:
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ("nan", "none", "") else None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> CanonicalTransaction:
        """
        Convert a raw India Synthetic row dict into a CanonicalTransaction.

        Parameters
        ----------
        row:
            Dict of column-name → value. May include columns from both
            transactions_features.csv and transactions_targets.csv.

        Returns
        -------
        CanonicalTransaction
        """
        raw_id = str(row["transaction_id"])

        amount_raw = row.get("amount_inr", 0)
        amount = Decimal(str(amount_raw)) if amount_raw is not None else Decimal("0")

        timestamp = cls._parse_timestamp(row.get("timestamp"))

        # --- Sender ------------------------------------------------------
        balance_before = cls._safe_decimal(row.get("account_balance_before"))
        balance_after = cls._safe_decimal(row.get("account_balance_after"))
        sender = AccountInfo(
            account_id=cls._safe_str(row.get("sender_account_id")),
            customer_id=cls._safe_str(row.get("sender_customer_id")),
            vpa=cls._safe_str(row.get("sender_vpa")),
            ifsc_code=cls._safe_str(row.get("sender_ifsc")),
            balance_before=balance_before,
            balance_after=balance_after,
        )

        # --- Receiver ----------------------------------------------------
        receiver = AccountInfo(
            account_id=cls._safe_str(row.get("receiver_account_id")),
            customer_id=cls._safe_str(row.get("receiver_customer_id")),
            vpa=cls._safe_str(row.get("receiver_vpa")),
            ifsc_code=cls._safe_str(row.get("receiver_ifsc")),
        )

        # --- Device ------------------------------------------------------
        device = DeviceInfo(
            device_id=cls._safe_str(row.get("device_id")),
            ip_address=cls._safe_str(row.get("ip_address")),
            is_new_device=cls._safe_bool(row.get("is_new_device")),
        )

        # --- Location ----------------------------------------------------
        location = GeoLocation(
            city=cls._safe_str(row.get("tx_city")),
            state=cls._safe_str(row.get("tx_state")),
            country="IN",
            latitude=cls._safe_float(row.get("tx_lat")),
            longitude=cls._safe_float(row.get("tx_long")),
        )

        # --- Metadata (features + optional targets) ----------------------
        metadata = TransactionMetadata(
            amount_ratio_vs_30d_avg=cls._safe_float(row.get("amount_ratio_vs_30d_avg")),
            tx_frequency_24h=cls._safe_int(row.get("tx_frequency_24h")),
            time_since_last_tx_sec=cls._safe_int(row.get("time_since_last_tx_sec")),
            distance_from_home_km=cls._safe_float(row.get("distance_from_home_km")),
            is_new_beneficiary=cls._safe_bool(row.get("is_new_beneficiary")),
            time_since_beneficiary_added_min=cls._safe_int(
                row.get("time_since_beneficiary_added_min")
            ),
            transaction_type=cls._safe_str(row.get("transaction_type")),
            # target columns (optional — present only in merged rows)
            scenario_id=cls._safe_str(row.get("scenario_id")),
            risk_label=cls._safe_str(row.get("risk_label")),
            alert_id=cls._safe_str(row.get("alert_id")),
            is_flagged_fraud=cls._safe_bool(row.get("is_flagged_alert")),
            extra={
                "day_of_month": row.get("day_of_month"),
                "hour_of_day": row.get("hour_of_day"),
                "day_of_week": row.get("day_of_week"),
            },
        )

        is_fraud: Optional[bool] = cls._safe_bool(row.get("is_fraud"))

        return CanonicalTransaction(
            raw_record_id=raw_id,
            source_dataset=DataSource.INDIA_SYNTHETIC,
            amount=amount,
            currency="INR",
            timestamp=timestamp,
            channel=cls._map_channel(cls._safe_str(row.get("channel"))),
            status=cls._map_status(cls._safe_str(row.get("status"))),
            sender=sender,
            receiver=receiver,
            device=device,
            location=location,
            is_fraud=is_fraud,
            metadata=metadata,
        )
