"""
Tests for src/ml/ieee_cis_loader.py

Verifies:
- load_ieee_cis raises FileNotFoundError when data is absent
- Merge logic (left join, key handling)
- Target column (isFraud) and TransactionID not in returned X
- isFraud is the actual target
- sample_frac reduces row count
"""

from __future__ import annotations

import pandas as pd
import pytest

from ml.ieee_cis_loader import (
    TRANSACTION_JOIN_KEY,
    TARGET_COLUMN,
    LEAKAGE_COLUMNS,
    load_ieee_cis,
)


class TestLoadIeeeCisMissingFiles:
    """load_ieee_cis must raise FileNotFoundError for missing data."""

    def test_raises_file_not_found_on_missing_dir(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        with pytest.raises(FileNotFoundError, match="ieee_cis"):
            load_ieee_cis(data_dir=missing)

    def test_raises_file_not_found_on_empty_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_ieee_cis(data_dir=tmp_path)


class TestLoadIeeeCisWithFixtureCSVs:
    """Test merge, leakage removal, and return types using small CSVs."""

    @pytest.fixture
    def ieee_cis_dir(self, tmp_path):
        """Create minimal train_transaction.csv and train_identity.csv."""
        tx = pd.DataFrame({
            "TransactionID": [1, 2, 3, 4, 5],
            "isFraud": [0, 1, 0, 0, 1],
            "TransactionAmt": [100.0, 250.0, 75.0, 500.0, 320.0],
            "ProductCD": ["W", "H", "W", "C", "H"],
            "card1": [1234, 5678, 1234, 9999, 5678],
        })
        identity = pd.DataFrame({
            "TransactionID": [1, 3],
            "DeviceType": ["desktop", "mobile"],
        })
        tx.to_csv(tmp_path / "train_transaction.csv", index=False)
        identity.to_csv(tmp_path / "train_identity.csv", index=False)
        return tmp_path

    def test_returns_dataframe_and_series(self, ieee_cis_dir):
        X, y = load_ieee_cis(data_dir=ieee_cis_dir)
        assert isinstance(X, pd.DataFrame)
        assert isinstance(y, pd.Series)

    def test_transaction_id_not_in_X(self, ieee_cis_dir):
        X, _ = load_ieee_cis(data_dir=ieee_cis_dir)
        assert TRANSACTION_JOIN_KEY not in X.columns

    def test_is_fraud_not_in_X(self, ieee_cis_dir):
        X, _ = load_ieee_cis(data_dir=ieee_cis_dir)
        assert TARGET_COLUMN not in X.columns

    def test_y_values_are_binary_integers(self, ieee_cis_dir):
        _, y = load_ieee_cis(data_dir=ieee_cis_dir)
        assert set(y.unique()).issubset({0, 1})
        assert y.dtype in (int, "int64", "int32")

    def test_left_join_preserves_all_transactions(self, ieee_cis_dir):
        X, y = load_ieee_cis(data_dir=ieee_cis_dir)
        assert len(X) == 5  # all 5 transactions retained

    def test_identity_columns_merged(self, ieee_cis_dir):
        X, _ = load_ieee_cis(data_dir=ieee_cis_dir)
        assert "DeviceType" in X.columns
        # Rows without identity data should have NaN for DeviceType
        assert X["DeviceType"].isna().sum() == 3

    def test_sample_frac_reduces_rows(self, ieee_cis_dir):
        X, y = load_ieee_cis(data_dir=ieee_cis_dir, sample_frac=0.4)
        assert len(X) < 5
        assert len(X) == len(y)

    def test_sample_frac_invalid_raises(self, ieee_cis_dir):
        with pytest.raises(ValueError, match="sample_frac"):
            load_ieee_cis(data_dir=ieee_cis_dir, sample_frac=1.5)

    def test_leakage_columns_constant(self):
        """TransactionID and isFraud must always be in LEAKAGE_COLUMNS."""
        assert "TransactionID" in LEAKAGE_COLUMNS
        assert "isFraud" in LEAKAGE_COLUMNS
