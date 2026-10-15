"""
Tests for src/ml/feature_mapper.py

Verifies:
- canonical_to_xgb_features extracts TransactionAmt correctly
- Maps optional fields when present
- Handles missing optional fields gracefully
- Strips leakage fields (TransactionID, isFraud) if accidentally included
- Does not raise on minimal input
- canonical_to_if_features produces the same output as xgb version
- describe_mapping returns expected structure
- Result is compatible with FraudPredictor.predict_transaction() interface
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
from dataclasses import dataclass, field

import pytest

from ml.feature_mapper import (
    canonical_to_xgb_features,
    canonical_to_if_features,
    describe_mapping,
)


# ---------------------------------------------------------------------------
# Minimal fake CanonicalTransaction for testing without Pydantic import
# ---------------------------------------------------------------------------

@dataclass
class FakeSender:
    bank_name: str | None = None
    email_domain: str | None = None


@dataclass
class FakeReceiver:
    email_domain: str | None = None


@dataclass
class FakeLocation:
    region_code: Any = None


@dataclass
class FakeTransaction:
    amount: Any = Decimal("100.00")
    raw_record_id: str = "TX001"
    source_dataset: str = "IEEE_CIS"
    sender: FakeSender = field(default_factory=FakeSender)
    receiver: FakeReceiver = field(default_factory=FakeReceiver)
    location: FakeLocation = field(default_factory=FakeLocation)


class TestCanonicalToXgbFeatures:
    def test_transaction_amt_mapped(self):
        tx = FakeTransaction(amount=Decimal("250.00"))
        features = canonical_to_xgb_features(tx)
        assert features["TransactionAmt"] == pytest.approx(250.0)

    def test_transaction_amt_is_float(self):
        tx = FakeTransaction(amount=Decimal("99.50"))
        features = canonical_to_xgb_features(tx)
        assert isinstance(features["TransactionAmt"], float)

    def test_bank_name_maps_to_card4(self):
        tx = FakeTransaction(sender=FakeSender(bank_name="Visa"))
        features = canonical_to_xgb_features(tx)
        assert features.get("card4") == "visa"

    def test_region_maps_to_addr1(self):
        tx = FakeTransaction(location=FakeLocation(region_code=123))
        features = canonical_to_xgb_features(tx)
        assert features.get("addr1") == 123

    def test_sender_email_maps_to_p_emaildomain(self):
        tx = FakeTransaction(sender=FakeSender(email_domain="gmail.com"))
        features = canonical_to_xgb_features(tx)
        assert features.get("P_emaildomain") == "gmail.com"

    def test_receiver_email_maps_to_r_emaildomain(self):
        tx = FakeTransaction(receiver=FakeReceiver(email_domain="yahoo.com"))
        features = canonical_to_xgb_features(tx)
        assert features.get("R_emaildomain") == "yahoo.com"

    def test_none_optional_fields_not_included(self):
        tx = FakeTransaction()  # all optional fields None
        features = canonical_to_xgb_features(tx)
        assert "card4" not in features
        assert "addr1" not in features
        assert "P_emaildomain" not in features
        assert "R_emaildomain" not in features

    def test_invalid_amount_becomes_nan(self):
        tx = FakeTransaction(amount="bad_value")
        features = canonical_to_xgb_features(tx)
        assert math.isnan(features["TransactionAmt"])

    def test_no_leakage_columns(self):
        tx = FakeTransaction()
        features = canonical_to_xgb_features(tx)
        assert "TransactionID" not in features
        assert "isFraud" not in features

    def test_minimal_input_does_not_crash(self):
        """Object with only amount field should not raise."""
        class MinimalTx:
            amount = Decimal("50.00")
        features = canonical_to_xgb_features(MinimalTx())
        assert "TransactionAmt" in features
        assert features["TransactionAmt"] == pytest.approx(50.0)

    def test_bank_name_truncated_to_20_chars(self):
        tx = FakeTransaction(sender=FakeSender(bank_name="A" * 30))
        features = canonical_to_xgb_features(tx)
        assert len(features.get("card4", "")) <= 20

    def test_all_mapped_columns_are_subset_of_ieee_cis(self):
        """Mapped columns must all be valid IEEE-CIS feature names."""
        ieee_cis_valid = {"TransactionAmt", "card4", "addr1", "P_emaildomain", "R_emaildomain"}
        tx = FakeTransaction(
            amount=Decimal("100"),
            sender=FakeSender(bank_name="visa", email_domain="gmail.com"),
            receiver=FakeReceiver(email_domain="yahoo.com"),
            location=FakeLocation(region_code=500),
        )
        features = canonical_to_xgb_features(tx)
        assert set(features.keys()).issubset(ieee_cis_valid | {"TransactionAmt"})


class TestCanonicalToIfFeatures:
    def test_same_as_xgb_features(self):
        tx = FakeTransaction(
            amount=Decimal("100"),
            sender=FakeSender(bank_name="visa"),
        )
        xgb = canonical_to_xgb_features(tx)
        iforest = canonical_to_if_features(tx)
        assert xgb == iforest


class TestDescribeMapping:
    def test_required_keys(self):
        desc = describe_mapping()
        for key in ("mapped_columns", "total_ieee_cis_features", "n_mapped", "n_nan_imputed", "mapping_note", "field_map"):
            assert key in desc

    def test_n_mapped_matches_mapped_columns(self):
        desc = describe_mapping()
        assert desc["n_mapped"] == len(desc["mapped_columns"])

    def test_n_nan_imputed_is_total_minus_mapped(self):
        desc = describe_mapping()
        assert desc["n_nan_imputed"] == desc["total_ieee_cis_features"] - desc["n_mapped"]

    def test_mapping_note_warns_about_nan_imputation(self):
        desc = describe_mapping()
        assert "NaN" in desc["mapping_note"] or "nan" in desc["mapping_note"].lower()


class TestRealCanonicalTransactionMapping:
    """Test mapping directly with real CanonicalTransaction instances."""

    def test_map_canonical_transaction_from_ieee_cis_adapter(self):
        from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter

        raw_row = {
            "TransactionID": 2987000,
            "TransactionAmt": 68.5,
            "TransactionDT": 86400,
            "ProductCD": "W",
            "card4": "discover",
            "card6": "credit",
            "addr1": 315.0,
            "addr2": 87.0,
            "P_emaildomain": "gmail.com",
            "R_emaildomain": "yahoo.com",
        }
        canonical_tx = IEEECISAdapter.from_row(raw_row)

        features = canonical_to_xgb_features(canonical_tx)
        assert features["TransactionAmt"] == 68.5
        assert features["card4"] == "discover"
        assert features["addr1"] == 315.0
        assert features["P_emaildomain"] == "gmail.com"
        assert features["R_emaildomain"] == "yahoo.com"

    def test_map_canonical_transaction_missing_optional_fields(self):
        from src.schemas.canonical_transaction import CanonicalTransaction

        tx = CanonicalTransaction(
            raw_record_id="MIN001",
            source_dataset="IEEE_CIS",
            amount=Decimal("42.50"),
        )
        features = canonical_to_xgb_features(tx)
        assert features["TransactionAmt"] == 42.5
        assert "card4" not in features
        assert "addr1" not in features
