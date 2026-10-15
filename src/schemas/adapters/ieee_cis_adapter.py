"""
Sentinel AI — IEEE-CIS Dataset Adapter

Converts a raw row from either:
  - train_transaction.csv  (or test_transaction.csv)
  - optionally merged with train_identity.csv

into a CanonicalTransaction.

IEEE-CIS schema highlights
--------------------------
Transaction file key columns:
  TransactionID   – integer primary key
  isFraud         – 0/1 label (absent in test split)
  TransactionDT   – seconds offset from a reference epoch (not a real timestamp)
  TransactionAmt  – USD amount
  ProductCD       – single-letter product code (W, H, C, S, R)
  card1..card6    – card-related categorical/numeric features
  addr1, addr2    – billing zip / country code
  P_emaildomain   – purchaser e-mail domain
  R_emaildomain   – recipient e-mail domain
  C1..C14         – count-type features (hashed; e.g. card count associated with address)
  D1..D15         – timedelta features
  M1..M9         – match features (T/F/M0..M9)
  V1..V339        – Vesta engineered features (hashed)

Identity file key columns:
  TransactionID   – foreign key to transaction file
  id_01..id_38    – network / device identity features
  DeviceType      – "desktop" or "mobile"
  DeviceInfo      – raw device string

Notes
-----
- TransactionDT is a delta in seconds from an unstated reference epoch.
  We store it as an integer offset; a None timestamp is valid and expected.
- The currency is USD per the Kaggle competition description.
- Sender/receiver account mapping: IEEE-CIS does not expose direct account
  IDs. We store card1 as a proxy sender account identifier and use
  P_emaildomain / R_emaildomain for party metadata.
- All column references are taken from the verified schema in DATASET_REGISTRY.md.
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


class IEEECISAdapter:
    """
    Adapts a single IEEE-CIS transaction row (merged or unmerged with identity)
    into a CanonicalTransaction.

    Usage
    -----
    ::

        row = {
            "TransactionID": 2987000,
            "TransactionAmt": 68.5,
            "TransactionDT": 86400,
            ...
        }
        canonical = IEEECISAdapter.from_row(row)
    """

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    _CARD_NETWORK_MAP: dict[str, str] = {
        "visa": "VISA",
        "mastercard": "MASTERCARD",
        "american express": "AMEX",
        "discover": "DISCOVER",
    }

    @classmethod
    def _map_channel(cls, product_cd: Optional[str]) -> TransactionChannel:
        """
        IEEE-CIS ProductCD is a 1-letter code for the transaction product.
        All transactions are effectively card-based online/e-commerce transactions.
        """
        # All IEEE-CIS transactions are card-based; ProductCD refines product type
        # but does not change the payment channel.
        return TransactionChannel.CARD

    @classmethod
    def _map_card_type(cls, card6: Any) -> Optional[str]:
        """card6 encodes credit/debit."""
        if card6 is None or (isinstance(card6, float) and card6 != card6):
            return None
        return str(card6).lower()

    @classmethod
    def _map_card_network(cls, card4: Any) -> Optional[str]:
        if card4 is None or (isinstance(card4, float) and card4 != card4):
            return None
        return cls._CARD_NETWORK_MAP.get(str(card4).lower().strip(), str(card4))

    @classmethod
    def _safe_str(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, float) and v != v:  # NaN check
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ("nan", "none", "") else None

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> CanonicalTransaction:
        """
        Convert a raw IEEE-CIS row dict into a CanonicalTransaction.

        Parameters
        ----------
        row:
            Dict of column-name → value from the IEEE-CIS CSV. May include
            merged identity columns (DeviceType, DeviceInfo, id_xx).

        Returns
        -------
        CanonicalTransaction
        """
        raw_id = str(row["TransactionID"])
        amount = Decimal(str(row.get("TransactionAmt", 0)))

        # --- Sender (purchaser proxy) ------------------------------------
        # IEEE-CIS does not expose raw account numbers; card1 is used as a
        # hashed card proxy identifier.
        sender = AccountInfo(
            account_id=cls._safe_str(row.get("card1")),
            email_domain=cls._safe_str(row.get("P_emaildomain")),
        )

        # --- Receiver (recipient proxy) ----------------------------------
        receiver = AccountInfo(
            email_domain=cls._safe_str(row.get("R_emaildomain")),
            # addr1 = billing zip (purchaser side); no direct receiver account
        )

        # --- Device ------------------------------------------------------
        device = DeviceInfo(
            device_type=cls._safe_str(row.get("DeviceType")),
            device_info=cls._safe_str(row.get("DeviceInfo")),
        )

        # --- Location (billing address proxy) ----------------------------
        zip_code = cls._safe_str(row.get("addr1"))
        location = GeoLocation(
            zip_code=zip_code,
            country=cls._safe_str(row.get("addr2")),
        )

        # --- Metadata ---------------------------------------------------
        metadata = TransactionMetadata(
            product_code=cls._safe_str(row.get("ProductCD")),
            card_type=cls._map_card_type(row.get("card6")),
            card_network=cls._map_card_network(row.get("card4")),
            is_flagged_fraud=cls._safe_bool(row.get("isFlaggedFraud")),
            extra={
                "TransactionDT": row.get("TransactionDT"),
                "card2": row.get("card2"),
                "card3": row.get("card3"),
                "card5": row.get("card5"),
                "dist1": row.get("dist1"),
                "dist2": row.get("dist2"),
            },
        )

        is_fraud_raw = row.get("isFraud")
        is_fraud: Optional[bool] = (
            cls._safe_bool(is_fraud_raw) if is_fraud_raw is not None else None
        )

        return CanonicalTransaction(
            raw_record_id=raw_id,
            source_dataset=DataSource.IEEE_CIS,
            amount=amount,
            currency="USD",
            timestamp=None,  # TransactionDT is a relative delta, not absolute
            channel=cls._map_channel(cls._safe_str(row.get("ProductCD"))),
            status=TransactionStatus.UNKNOWN,  # IEEE-CIS has no settlement status
            sender=sender,
            receiver=receiver,
            device=device,
            location=location,
            is_fraud=is_fraud,
            metadata=metadata,
        )
