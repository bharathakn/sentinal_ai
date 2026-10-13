"""
Sentinel AI — Canonical Schema Tests
======================================

Tests that verify:
  1. The CanonicalTransaction Pydantic model validates correctly.
  2. Each dataset adapter (IEEE-CIS, PaySim, India Synthetic) converts sample
     rows into valid CanonicalTransaction instances.
  3. Sample rows representative of real data are fed through the pipeline and
     all fields are mapped correctly.
  4. Validation rules reject invalid inputs.

Running
-------
From the project root::

    python -m pytest tests/test_canonical_schema.py -v

Or directly::

    python tests/test_canonical_schema.py
"""

from __future__ import annotations

import sys
import os

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from project root without install
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from uuid import UUID

from pydantic import ValidationError

from src.schemas.canonical_transaction import (
    AccountInfo,
    CanonicalTransaction,
    DataSource,
    DeviceInfo,
    GeoLocation,
    TransactionChannel,
    TransactionMetadata,
    TransactionStatus,
)
from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter
from src.schemas.adapters.paysim_adapter import PaySimAdapter
from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter


# ===========================================================================
# Sample raw rows  —  representative of actual dataset contents
# ===========================================================================

# ---------------------------------------------------------------------------
# IEEE-CIS: representative row from train_transaction.csv row 1 (merged with
# a plausible identity row). Verified against actual CSV header inspection.
# ---------------------------------------------------------------------------
IEEE_CIS_SAMPLE_ROW: dict = {
    "TransactionID": 2987000,
    "isFraud": 0,
    "TransactionDT": 86400,
    "TransactionAmt": 68.5,
    "ProductCD": "W",
    "card1": 13926,
    "card2": None,
    "card3": 150.0,
    "card4": "discover",
    "card5": 142.0,
    "card6": "credit",
    "addr1": 315.0,
    "addr2": 87.0,
    "dist1": 19.0,
    "dist2": None,
    "P_emaildomain": None,
    "R_emaildomain": None,
    # Identity columns (merged)
    "DeviceType": "desktop",
    "DeviceInfo": "Windows",
    # isFlaggedFraud not present in train_transaction but for test completeness:
    "isFlaggedFraud": 0,
}

IEEE_CIS_SAMPLE_FRAUD_ROW: dict = {
    "TransactionID": 2987001,
    "isFraud": 1,
    "TransactionDT": 86401,
    "TransactionAmt": 29.0,
    "ProductCD": "W",
    "card1": 2755,
    "card2": 404.0,
    "card3": 150.0,
    "card4": "mastercard",
    "card5": 102.0,
    "card6": "credit",
    "addr1": 325.0,
    "addr2": 87.0,
    "dist1": None,
    "dist2": None,
    "P_emaildomain": "gmail.com",
    "R_emaildomain": None,
    "DeviceType": "mobile",
    "DeviceInfo": "iOS Device",
    "isFlaggedFraud": 0,
}

# ---------------------------------------------------------------------------
# PaySim: representative rows from the PaySim CSV (verified header).
# ---------------------------------------------------------------------------
PAYSIM_PAYMENT_ROW: dict = {
    "step": 1,
    "type": "PAYMENT",
    "amount": 9839.64,
    "nameOrig": "C1231006815",
    "oldbalanceOrg": 170136.0,
    "newbalanceOrig": 160296.36,
    "nameDest": "M1979787155",
    "oldbalanceDest": 0.0,
    "newbalanceDest": 0.0,
    "isFraud": 0,
    "isFlaggedFraud": 0,
}

PAYSIM_TRANSFER_FRAUD_ROW: dict = {
    "step": 206,
    "type": "TRANSFER",
    "amount": 215310.30,
    "nameOrig": "C1503601248",
    "oldbalanceOrg": 215310.30,
    "newbalanceOrig": 0.0,
    "nameDest": "C1364872998",
    "oldbalanceDest": 0.0,
    "newbalanceDest": 0.0,
    "isFraud": 1,
    "isFlaggedFraud": 1,
}

PAYSIM_CASHOUT_ROW: dict = {
    "step": 1,
    "type": "CASH_OUT",
    "amount": 1864.28,
    "nameOrig": "C1666544295",
    "oldbalanceOrg": 21249.0,
    "newbalanceOrig": 19384.72,
    "nameDest": "C2044282225",
    "oldbalanceDest": 0.0,
    "newbalanceDest": 0.0,
    "isFraud": 0,
    "isFlaggedFraud": 0,
}

# ---------------------------------------------------------------------------
# India Synthetic: representative rows from transactions_features.csv
# merged with transactions_targets.csv (verified header).
# ---------------------------------------------------------------------------
INDIA_UPI_ROW: dict = {
    # features
    "transaction_id": "TXN_IND_202608_000002",
    "timestamp": "2026-08-15T06:48:56+05:30",
    "day_of_month": 15,
    "hour_of_day": 6,
    "day_of_week": 5,
    "channel": "UPI",
    "transaction_type": "P2P",
    "amount_inr": 374.62,
    "status": "SUCCESS",
    "sender_account_id": "ACC_IND_001057",
    "receiver_account_id": "ACC_IND_000118",
    "sender_customer_id": "CUST_IND_001057",
    "receiver_customer_id": "CUST_IND_000118",
    "sender_vpa": "user001057@okicici",
    "receiver_vpa": "user000118@okicici",
    "sender_ifsc": "BOB0003110",
    "receiver_ifsc": "AXIS0003700",
    "device_id": "DEV_IND_001057",
    "ip_address": "103.136.57.94",
    "tx_city": "Patna",
    "tx_state": "Bihar",
    "tx_lat": 25.6365,
    "tx_long": 85.104,
    "distance_from_home_km": 12.12,
    "is_new_device": 1,
    "is_new_beneficiary": 0,
    "time_since_beneficiary_added_min": 39485,
    "amount_ratio_vs_30d_avg": 0.2794,
    "tx_frequency_24h": 4,
    "time_since_last_tx_sec": 61038,
    "account_balance_before": 5616.48,
    "account_balance_after": 5241.86,
    # targets (merged)
    "alert_id": "ALT_202608_000002",
    "is_fraud": 0,
    "risk_label": "LOW_RISK",
    "is_flagged_alert": 0,
    "scenario_id": "SCENARIO_1_NORMAL_LEGITIMATE",
}

INDIA_NEFT_ROW: dict = {
    "transaction_id": "TXN_IND_202608_000001",
    "timestamp": "2026-08-09T17:55:21+05:30",
    "day_of_month": 9,
    "hour_of_day": 17,
    "day_of_week": 6,
    "channel": "NEFT",
    "transaction_type": "C2B",
    "amount_inr": 5373.78,
    "status": "SUCCESS",
    "sender_account_id": "ACC_IND_001038",
    "receiver_account_id": "ACC_IND_001162",
    "sender_customer_id": "CUST_IND_001038",
    "receiver_customer_id": "CUST_IND_001162",
    "sender_vpa": "user001038@oksbi",
    "receiver_vpa": "user001162@oksbi",
    "sender_ifsc": "BOB0001381",
    "receiver_ifsc": "HDFC0004879",
    "device_id": "DEV_IND_001038",
    "ip_address": "103.125.199.101",
    "tx_city": "Mumbai",
    "tx_state": "Maharashtra",
    "tx_lat": 19.1244,
    "tx_long": 72.8968,
    "distance_from_home_km": 7.35,
    "is_new_device": 0,
    "is_new_beneficiary": 0,
    "time_since_beneficiary_added_min": 27490,
    "amount_ratio_vs_30d_avg": 0.6114,
    "tx_frequency_24h": 8,
    "time_since_last_tx_sec": 69470,
    "account_balance_before": 66470.62,
    "account_balance_after": 61096.84,
    # targets
    "alert_id": "ALT_202608_000001",
    "is_fraud": 0,
    "risk_label": "LOW_RISK",
    "is_flagged_alert": 0,
    "scenario_id": "SCENARIO_1_NORMAL_LEGITIMATE",
}

INDIA_RTGS_FRAUD_ROW: dict = {
    "transaction_id": "TXN_IND_202608_009001",
    "timestamp": "2026-08-20T14:22:10+05:30",
    "day_of_month": 20,
    "hour_of_day": 14,
    "day_of_week": 3,
    "channel": "RTGS",
    "transaction_type": "P2P",
    "amount_inr": 450000.00,
    "status": "SUCCESS",
    "sender_account_id": "ACC_IND_000999",
    "receiver_account_id": "ACC_IND_000001",
    "sender_customer_id": "CUST_IND_000999",
    "receiver_customer_id": "CUST_IND_000001",
    "sender_vpa": "user000999@oksbi",
    "receiver_vpa": "user000001@okhdfc",
    "sender_ifsc": "SBI0009991",
    "receiver_ifsc": "HDFC0000011",
    "device_id": "DEV_IND_000999",
    "ip_address": "192.168.10.50",
    "tx_city": "Delhi",
    "tx_state": "Delhi",
    "tx_lat": 28.6139,
    "tx_long": 77.2090,
    "distance_from_home_km": 1580.0,
    "is_new_device": 1,
    "is_new_beneficiary": 1,
    "time_since_beneficiary_added_min": 12,
    "amount_ratio_vs_30d_avg": 10.2,
    "tx_frequency_24h": 15,
    "time_since_last_tx_sec": 180,
    "account_balance_before": 520000.0,
    "account_balance_after": 70000.0,
    # targets
    "alert_id": "ALT_202608_009001",
    "is_fraud": 1,
    "risk_label": "HIGH_RISK",
    "is_flagged_alert": 1,
    "scenario_id": "SCENARIO_7_LAYERING_NETWORK",
}


# ===========================================================================
# Test Cases
# ===========================================================================


class TestCanonicalTransactionModel(unittest.TestCase):
    """Unit tests for the CanonicalTransaction Pydantic model itself."""

    def _minimal_canonical(self, **overrides) -> dict:
        base = {
            "raw_record_id": "TEST_001",
            "source_dataset": DataSource.IEEE_CIS,
            "amount": Decimal("100.00"),
        }
        base.update(overrides)
        return base

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_minimal_construction(self):
        """CanonicalTransaction can be built with only required fields."""
        tx = CanonicalTransaction(**self._minimal_canonical())
        self.assertIsInstance(tx.canonical_id, UUID)
        self.assertEqual(tx.raw_record_id, "TEST_001")
        self.assertEqual(tx.amount, Decimal("100.00"))
        self.assertEqual(tx.currency, "USD")  # default
        self.assertIsNone(tx.is_fraud)

    def test_canonical_id_auto_generated(self):
        """Each instance gets a unique UUID."""
        tx1 = CanonicalTransaction(**self._minimal_canonical())
        tx2 = CanonicalTransaction(**self._minimal_canonical())
        self.assertNotEqual(tx1.canonical_id, tx2.canonical_id)

    def test_currency_uppercased(self):
        """Currency code is always uppercased."""
        tx = CanonicalTransaction(**self._minimal_canonical(currency="inr"))
        self.assertEqual(tx.currency, "INR")

    def test_amount_zero_valid(self):
        """Zero amount is a valid transaction (e.g. balance enquiries / failed txns)."""
        tx = CanonicalTransaction(**self._minimal_canonical(amount=Decimal("0")))
        self.assertEqual(tx.amount, Decimal("0"))

    def test_amount_string_coercion(self):
        """Amount can be supplied as a numeric string."""
        tx = CanonicalTransaction(**self._minimal_canonical(amount="250.75"))
        self.assertEqual(tx.amount, Decimal("250.75"))

    def test_is_fraud_none_for_unlabelled(self):
        """is_fraud is None for test/live data that has no label."""
        tx = CanonicalTransaction(**self._minimal_canonical())
        self.assertIsNone(tx.is_fraud)

    def test_is_fraud_true_false(self):
        """is_fraud can be True or False for labelled data."""
        tx_fraud = CanonicalTransaction(**self._minimal_canonical(is_fraud=True))
        tx_legit = CanonicalTransaction(**self._minimal_canonical(is_fraud=False))
        self.assertTrue(tx_fraud.is_fraud)
        self.assertFalse(tx_legit.is_fraud)

    # ------------------------------------------------------------------
    # Validation failures
    # ------------------------------------------------------------------

    def test_negative_amount_rejected(self):
        """Negative amounts are rejected by the Pydantic validator."""
        with self.assertRaises(ValidationError):
            CanonicalTransaction(**self._minimal_canonical(amount=Decimal("-10.00")))

    def test_empty_raw_record_id_rejected(self):
        """Empty raw_record_id is rejected."""
        with self.assertRaises(ValidationError):
            CanonicalTransaction(**self._minimal_canonical(raw_record_id=""))

    def test_whitespace_raw_record_id_rejected(self):
        """Whitespace-only raw_record_id is rejected."""
        with self.assertRaises(ValidationError):
            CanonicalTransaction(**self._minimal_canonical(raw_record_id="   "))

    def test_invalid_latitude_rejected(self):
        """Latitude outside [-90, 90] is rejected."""
        with self.assertRaises(ValidationError):
            GeoLocation(latitude=91.0)

    def test_invalid_longitude_rejected(self):
        """Longitude outside [-180, 180] is rejected."""
        with self.assertRaises(ValidationError):
            GeoLocation(longitude=-181.0)

    def test_currency_too_short_rejected(self):
        """Currency code with fewer than 3 characters is rejected."""
        with self.assertRaises(ValidationError):
            CanonicalTransaction(**self._minimal_canonical(currency="US"))

    def test_currency_too_long_rejected(self):
        """Currency code with more than 3 characters is rejected."""
        with self.assertRaises(ValidationError):
            CanonicalTransaction(**self._minimal_canonical(currency="USDX"))

    # ------------------------------------------------------------------
    # Sub-models
    # ------------------------------------------------------------------

    def test_geo_location_valid(self):
        loc = GeoLocation(city="Mumbai", state="Maharashtra", country="IN",
                          latitude=19.07, longitude=72.87)
        self.assertEqual(loc.city, "Mumbai")
        self.assertEqual(loc.latitude, 19.07)

    def test_device_info_valid(self):
        dev = DeviceInfo(device_id="DEV_001", device_type="mobile", is_new_device=True)
        self.assertTrue(dev.is_new_device)

    def test_account_info_valid(self):
        acc = AccountInfo(account_id="ACC_001", vpa="user@okicici",
                          balance_before=Decimal("5000"), balance_after=Decimal("4000"))
        self.assertEqual(acc.vpa, "user@okicici")

    def test_transaction_metadata_extra(self):
        meta = TransactionMetadata(extra={"custom_key": "custom_value"})
        self.assertEqual(meta.extra["custom_key"], "custom_value")


# ---------------------------------------------------------------------------
# IEEE-CIS Adapter Tests
# ---------------------------------------------------------------------------


class TestIEEECISAdapter(unittest.TestCase):
    """Tests for the IEEE-CIS adapter."""

    def test_normal_transaction_converts(self):
        """Standard IEEE-CIS row converts to a valid CanonicalTransaction."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertIsInstance(tx, CanonicalTransaction)
        self.assertEqual(tx.source_dataset, DataSource.IEEE_CIS)
        self.assertEqual(tx.raw_record_id, "2987000")
        self.assertEqual(tx.amount, Decimal("68.5"))
        self.assertEqual(tx.currency, "USD")
        self.assertFalse(tx.is_fraud)

    def test_fraud_row_converts(self):
        """Fraudulent IEEE-CIS row has is_fraud=True."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_FRAUD_ROW)
        self.assertTrue(tx.is_fraud)
        self.assertEqual(tx.raw_record_id, "2987001")

    def test_channel_is_card(self):
        """All IEEE-CIS transactions map to CARD channel."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.channel, TransactionChannel.CARD)

    def test_timestamp_is_none(self):
        """IEEE-CIS TransactionDT is a relative offset, so timestamp is None."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertIsNone(tx.timestamp)

    def test_device_type_mapped(self):
        """DeviceType from identity is preserved."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.device.device_type, "desktop")

    def test_card_network_mapped(self):
        """card4 (e.g. 'discover') is mapped to card_network in metadata."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.metadata.card_network, "DISCOVER")

    def test_card_type_mapped(self):
        """card6 ('credit') is mapped to card_type in metadata."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.metadata.card_type, "credit")

    def test_mastercard_row(self):
        """Mastercard card network is mapped correctly."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_FRAUD_ROW)
        self.assertEqual(tx.metadata.card_network, "MASTERCARD")

    def test_product_code_in_metadata(self):
        """ProductCD is stored in metadata.product_code."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.metadata.product_code, "W")

    def test_status_is_unknown(self):
        """IEEE-CIS has no settlement status; status defaults to UNKNOWN."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.status, TransactionStatus.UNKNOWN)

    def test_sender_account_from_card1(self):
        """card1 is used as proxy sender account_id."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.sender.account_id, "13926")

    def test_email_domain_mapped(self):
        """P_emaildomain is mapped to sender email_domain."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_FRAUD_ROW)
        self.assertEqual(tx.sender.email_domain, "gmail.com")

    def test_nan_email_becomes_none(self):
        """NaN email domain maps to None, not 'nan'."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertIsNone(tx.sender.email_domain)

    def test_transactiondt_preserved_in_extra(self):
        """TransactionDT is preserved in metadata.extra for downstream ML use."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.metadata.extra["TransactionDT"], 86400)

    def test_zip_code_in_location(self):
        """addr1 (billing zip) is stored as zip_code in location."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertEqual(tx.location.zip_code, "315.0")

    def test_uuid_is_valid(self):
        """canonical_id is a valid UUID."""
        tx = IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW)
        self.assertIsInstance(tx.canonical_id, UUID)


# ---------------------------------------------------------------------------
# PaySim Adapter Tests
# ---------------------------------------------------------------------------


class TestPaySimAdapter(unittest.TestCase):
    """Tests for the PaySim adapter."""

    def test_payment_row_converts(self):
        """Standard PaySim PAYMENT row converts to CanonicalTransaction."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW, row_index=0)
        self.assertIsInstance(tx, CanonicalTransaction)
        self.assertEqual(tx.source_dataset, DataSource.PAYSIM)
        self.assertEqual(tx.amount, Decimal("9839.64"))
        self.assertEqual(tx.currency, "USD")
        self.assertFalse(tx.is_fraud)

    def test_transfer_fraud_row_converts(self):
        """PaySim TRANSFER (fraud) row converts correctly."""
        tx = PaySimAdapter.from_row(PAYSIM_TRANSFER_FRAUD_ROW, row_index=1)
        self.assertTrue(tx.is_fraud)
        self.assertTrue(tx.metadata.is_flagged_fraud)
        self.assertEqual(tx.amount, Decimal("215310.30"))

    def test_cashout_row_converts(self):
        """PaySim CASH_OUT row converts correctly."""
        tx = PaySimAdapter.from_row(PAYSIM_CASHOUT_ROW, row_index=2)
        self.assertEqual(tx.channel, TransactionChannel.CASH_OUT)

    def test_channel_payment(self):
        """PAYMENT type maps to PAYMENT channel."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertEqual(tx.channel, TransactionChannel.PAYMENT)

    def test_channel_transfer(self):
        """TRANSFER type maps to TRANSFER channel."""
        tx = PaySimAdapter.from_row(PAYSIM_TRANSFER_FRAUD_ROW)
        self.assertEqual(tx.channel, TransactionChannel.TRANSFER)

    def test_timestamp_is_none(self):
        """PaySim has no real timestamps; timestamp is None."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertIsNone(tx.timestamp)

    def test_step_in_metadata(self):
        """Simulation step is preserved in metadata.paysim_step."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertEqual(tx.metadata.paysim_step, 1)

    def test_sender_account_name(self):
        """nameOrig is stored as sender account_id and account_name."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertEqual(tx.sender.account_id, "C1231006815")
        self.assertEqual(tx.sender.account_name, "C1231006815")

    def test_receiver_account_name(self):
        """nameDest is stored as receiver account_id."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertEqual(tx.receiver.account_id, "M1979787155")

    def test_sender_balance_before(self):
        """oldbalanceOrg is mapped to sender.balance_before."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertEqual(tx.sender.balance_before, Decimal("170136.0"))

    def test_sender_balance_after(self):
        """newbalanceOrig is mapped to sender.balance_after."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertEqual(tx.sender.balance_after, Decimal("160296.36"))

    def test_raw_record_id_contains_name_orig(self):
        """Synthesised raw_record_id includes nameOrig for traceability."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW, row_index=0)
        self.assertIn("C1231006815", tx.raw_record_id)

    def test_no_location(self):
        """PaySim has no location data; location fields are all None."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertIsNone(tx.location.city)
        self.assertIsNone(tx.location.latitude)

    def test_no_device(self):
        """PaySim has no device data; device fields are all None."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertIsNone(tx.device.device_id)
        self.assertIsNone(tx.device.device_type)

    def test_status_is_unknown(self):
        """PaySim has no settlement status; status defaults to UNKNOWN."""
        tx = PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW)
        self.assertEqual(tx.status, TransactionStatus.UNKNOWN)


# ---------------------------------------------------------------------------
# India Synthetic Adapter Tests
# ---------------------------------------------------------------------------


class TestIndiaSyntheticAdapter(unittest.TestCase):
    """Tests for the India Synthetic adapter."""

    def test_upi_row_converts(self):
        """India UPI row converts to CanonicalTransaction."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertIsInstance(tx, CanonicalTransaction)
        self.assertEqual(tx.source_dataset, DataSource.INDIA_SYNTHETIC)
        self.assertEqual(tx.raw_record_id, "TXN_IND_202608_000002")
        self.assertEqual(tx.amount, Decimal("374.62"))
        self.assertEqual(tx.currency, "INR")
        self.assertFalse(tx.is_fraud)

    def test_neft_row_converts(self):
        """India NEFT row converts correctly."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_NEFT_ROW)
        self.assertEqual(tx.channel, TransactionChannel.NEFT)
        self.assertEqual(tx.amount, Decimal("5373.78"))

    def test_rtgs_fraud_row_converts(self):
        """India RTGS fraud row converts correctly with is_fraud=True."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_RTGS_FRAUD_ROW)
        self.assertEqual(tx.channel, TransactionChannel.RTGS)
        self.assertTrue(tx.is_fraud)
        self.assertEqual(tx.metadata.risk_label, "HIGH_RISK")

    def test_upi_channel_mapped(self):
        """UPI channel string maps to UPI enum."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.channel, TransactionChannel.UPI)

    def test_timestamp_parsed(self):
        """ISO-8601 timestamp is parsed correctly including timezone offset."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertIsNotNone(tx.timestamp)
        self.assertEqual(tx.timestamp.year, 2026)
        self.assertEqual(tx.timestamp.month, 8)
        self.assertEqual(tx.timestamp.day, 15)
        self.assertEqual(tx.timestamp.hour, 6)

    def test_currency_is_inr(self):
        """India Synthetic transactions use INR currency."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_NEFT_ROW)
        self.assertEqual(tx.currency, "INR")

    def test_sender_fields_mapped(self):
        """Sender account, customer, VPA, IFSC are all mapped."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.sender.account_id, "ACC_IND_001057")
        self.assertEqual(tx.sender.customer_id, "CUST_IND_001057")
        self.assertEqual(tx.sender.vpa, "user001057@okicici")
        self.assertEqual(tx.sender.ifsc_code, "BOB0003110")

    def test_receiver_fields_mapped(self):
        """Receiver account, customer, VPA, IFSC are all mapped."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.receiver.account_id, "ACC_IND_000118")
        self.assertEqual(tx.receiver.ifsc_code, "AXIS0003700")

    def test_device_fields_mapped(self):
        """Device ID, IP address, and is_new_device are mapped."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.device.device_id, "DEV_IND_001057")
        self.assertEqual(tx.device.ip_address, "103.136.57.94")
        self.assertTrue(tx.device.is_new_device)

    def test_location_fields_mapped(self):
        """City, state, lat, long are all mapped."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.location.city, "Patna")
        self.assertEqual(tx.location.state, "Bihar")
        self.assertEqual(tx.location.country, "IN")
        self.assertAlmostEqual(tx.location.latitude, 25.6365)
        self.assertAlmostEqual(tx.location.longitude, 85.104)

    def test_balance_fields_mapped(self):
        """Sender balance before/after are mapped."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_NEFT_ROW)
        self.assertEqual(tx.sender.balance_before, Decimal("66470.62"))
        self.assertEqual(tx.sender.balance_after, Decimal("61096.84"))

    def test_behavioral_features_in_metadata(self):
        """Behavioral ML features are preserved in metadata."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertAlmostEqual(tx.metadata.amount_ratio_vs_30d_avg, 0.2794)
        self.assertEqual(tx.metadata.tx_frequency_24h, 4)
        self.assertEqual(tx.metadata.time_since_last_tx_sec, 61038)
        self.assertAlmostEqual(tx.metadata.distance_from_home_km, 12.12)
        self.assertFalse(tx.metadata.is_new_beneficiary)

    def test_scenario_id_in_metadata(self):
        """scenario_id from targets is stored in metadata."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.metadata.scenario_id, "SCENARIO_1_NORMAL_LEGITIMATE")

    def test_alert_id_in_metadata(self):
        """alert_id is stored in metadata."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_NEFT_ROW)
        self.assertEqual(tx.metadata.alert_id, "ALT_202608_000001")

    def test_status_success(self):
        """SUCCESS status is correctly mapped."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.status, TransactionStatus.SUCCESS)

    def test_flagged_alert_in_metadata(self):
        """is_flagged_alert is stored as metadata.is_flagged_fraud."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_RTGS_FRAUD_ROW)
        self.assertTrue(tx.metadata.is_flagged_fraud)

    def test_new_beneficiary_time_in_metadata(self):
        """time_since_beneficiary_added_min is preserved."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_RTGS_FRAUD_ROW)
        self.assertEqual(tx.metadata.time_since_beneficiary_added_min, 12)

    def test_transaction_type_in_metadata(self):
        """transaction_type (P2P / C2B) is preserved in metadata."""
        tx = IndiaSyntheticAdapter.from_row(INDIA_UPI_ROW)
        self.assertEqual(tx.metadata.transaction_type, "P2P")

    def test_features_only_row_no_targets(self):
        """Adapter works with features-only row (no target columns)."""
        features_only = {
            k: v for k, v in INDIA_NEFT_ROW.items()
            if k not in {"alert_id", "is_fraud", "risk_label", "is_flagged_alert", "scenario_id"}
        }
        tx = IndiaSyntheticAdapter.from_row(features_only)
        self.assertIsNone(tx.is_fraud)
        self.assertIsNone(tx.metadata.scenario_id)
        self.assertIsNone(tx.metadata.alert_id)


# ---------------------------------------------------------------------------
# Cross-Dataset Compatibility Tests
# ---------------------------------------------------------------------------


class TestCrossDatasetCompatibility(unittest.TestCase):
    """
    Tests that verify all three adapters produce CanonicalTransaction instances
    that share the same schema and can be processed uniformly.
    """

    def _all_three_transactions(self):
        return [
            IEEECISAdapter.from_row(IEEE_CIS_SAMPLE_ROW),
            PaySimAdapter.from_row(PAYSIM_PAYMENT_ROW, row_index=0),
            IndiaSyntheticAdapter.from_row(INDIA_NEFT_ROW),
        ]

    def test_all_produce_canonical_transaction(self):
        """All three adapters produce CanonicalTransaction instances."""
        for tx in self._all_three_transactions():
            self.assertIsInstance(tx, CanonicalTransaction)

    def test_all_have_unique_canonical_ids(self):
        """Each canonical transaction has a unique canonical_id."""
        ids = [tx.canonical_id for tx in self._all_three_transactions()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_have_raw_record_id(self):
        """Every canonical transaction has a non-empty raw_record_id."""
        for tx in self._all_three_transactions():
            self.assertTrue(tx.raw_record_id)
            self.assertTrue(tx.raw_record_id.strip())

    def test_all_have_source_dataset(self):
        """Every canonical transaction has a source_dataset set."""
        txs = self._all_three_transactions()
        self.assertEqual(txs[0].source_dataset, DataSource.IEEE_CIS)
        self.assertEqual(txs[1].source_dataset, DataSource.PAYSIM)
        self.assertEqual(txs[2].source_dataset, DataSource.INDIA_SYNTHETIC)

    def test_all_have_positive_amount(self):
        """Every canonical transaction has a non-negative amount."""
        for tx in self._all_three_transactions():
            self.assertGreaterEqual(tx.amount, Decimal("0"))

    def test_all_have_valid_currency(self):
        """Every canonical transaction has a 3-character ISO currency code."""
        for tx in self._all_three_transactions():
            self.assertEqual(len(tx.currency), 3)
            self.assertTrue(tx.currency.isupper())

    def test_all_have_channel(self):
        """Every canonical transaction has a channel (not None)."""
        for tx in self._all_three_transactions():
            self.assertIsNotNone(tx.channel)
            self.assertIn(tx.channel, [c.value for c in TransactionChannel])

    def test_all_have_sender_sub_model(self):
        """Every canonical transaction has an AccountInfo sender sub-model."""
        for tx in self._all_three_transactions():
            self.assertIsInstance(tx.sender, AccountInfo)

    def test_all_have_receiver_sub_model(self):
        """Every canonical transaction has an AccountInfo receiver sub-model."""
        for tx in self._all_three_transactions():
            self.assertIsInstance(tx.receiver, AccountInfo)

    def test_all_have_device_sub_model(self):
        """Every canonical transaction has a DeviceInfo sub-model."""
        for tx in self._all_three_transactions():
            self.assertIsInstance(tx.device, DeviceInfo)

    def test_all_have_location_sub_model(self):
        """Every canonical transaction has a GeoLocation sub-model."""
        for tx in self._all_three_transactions():
            self.assertIsInstance(tx.location, GeoLocation)

    def test_all_have_metadata_sub_model(self):
        """Every canonical transaction has a TransactionMetadata sub-model."""
        for tx in self._all_three_transactions():
            self.assertIsInstance(tx.metadata, TransactionMetadata)

    def test_dict_serialisation(self):
        """All canonical transactions can be serialised to dict without error."""
        for tx in self._all_three_transactions():
            data = tx.model_dump()
            self.assertIn("canonical_id", data)
            self.assertIn("raw_record_id", data)
            self.assertIn("amount", data)

    def test_json_serialisation(self):
        """All canonical transactions can be serialised to JSON without error."""
        for tx in self._all_three_transactions():
            json_str = tx.model_dump_json()
            self.assertIn("canonical_id", json_str)
            self.assertIsInstance(json_str, str)
            self.assertGreater(len(json_str), 10)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCanonicalTransactionModel))
    suite.addTests(loader.loadTestsFromTestCase(TestIEEECISAdapter))
    suite.addTests(loader.loadTestsFromTestCase(TestPaySimAdapter))
    suite.addTests(loader.loadTestsFromTestCase(TestIndiaSyntheticAdapter))
    suite.addTests(loader.loadTestsFromTestCase(TestCrossDatasetCompatibility))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
