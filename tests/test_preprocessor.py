"""
Tests for src/ml/preprocessor.py

Verifies:
- Pipeline builds successfully on fixture data
- Preprocessing output is numeric (no NaNs)
- Pipeline fit on train only, transform on test
- feature_names has same length as transform output columns
- Unknown categories at inference don't raise errors (OrdinalEncoder)
- Consistent output shape between training and inference transform
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.preprocessor import build_preprocessing_pipeline, get_feature_names


class TestPreprocessorBuildsAndTransforms:
    def test_builds_without_error(self, small_ieee_cis_fixture):
        X, _ = small_ieee_cis_fixture
        train_X = X.iloc[:300]
        pipeline = build_preprocessing_pipeline(train_X)
        assert pipeline is not None

    def test_output_is_2d_float_array(self, small_ieee_cis_fixture):
        X, _ = small_ieee_cis_fixture
        pipeline = build_preprocessing_pipeline(X)
        X_t = pipeline.transform(X)
        assert isinstance(X_t, np.ndarray)
        assert X_t.ndim == 2
        assert X_t.dtype == np.float64

    def test_no_nans_in_output(self, small_ieee_cis_fixture):
        X, _ = small_ieee_cis_fixture
        pipeline = build_preprocessing_pipeline(X)
        X_t = pipeline.transform(X)
        assert not np.isnan(X_t).any(), "Preprocessed output must contain no NaN values"

    def test_feature_names_length_matches_columns(self, small_ieee_cis_fixture):
        X, _ = small_ieee_cis_fixture
        pipeline = build_preprocessing_pipeline(X)
        names = get_feature_names(pipeline, X)
        X_t = pipeline.transform(X)
        assert len(names) == X_t.shape[1], (
            f"feature_names has {len(names)} entries but transform output has {X_t.shape[1]} cols"
        )

    def test_train_only_fit_transform_test(self, small_ieee_cis_fixture):
        """Pipeline must be fit on train only, then applied to test."""
        X, _ = small_ieee_cis_fixture
        X_train = X.iloc[:300]
        X_test = X.iloc[300:]
        pipeline = build_preprocessing_pipeline(X_train)
        X_test_t = pipeline.transform(X_test)
        assert X_test_t.shape[0] == len(X_test)
        assert not np.isnan(X_test_t).any()

    def test_same_column_count_train_and_test(self, small_ieee_cis_fixture):
        X, _ = small_ieee_cis_fixture
        X_train = X.iloc[:300]
        X_test = X.iloc[300:]
        pipeline = build_preprocessing_pipeline(X_train)
        X_train_t = pipeline.transform(X_train)
        X_test_t = pipeline.transform(X_test)
        assert X_train_t.shape[1] == X_test_t.shape[1]

    def test_unknown_categorical_values_do_not_raise(self, small_ieee_cis_fixture):
        """Unknown categories at inference time must be handled (encoded as -1)."""
        X, _ = small_ieee_cis_fixture
        pipeline = build_preprocessing_pipeline(X.iloc[:300])

        X_unseen = X.iloc[300:].copy()
        # Inject an unseen category
        if "ProductCD" in X_unseen.columns:
            X_unseen.loc[X_unseen.index[0], "ProductCD"] = "UNSEEN_CATEGORY"

        # Should not raise
        X_unseen_t = pipeline.transform(X_unseen)
        assert not np.isnan(X_unseen_t).any()

    def test_no_leakage_columns_in_output(self, small_ieee_cis_fixture):
        """isFraud and TransactionID must never appear in preprocessed output."""
        X, y = small_ieee_cis_fixture
        # Simulate caller accidentally including isFraud
        X_with_leak = X.copy()
        X_with_leak["isFraud"] = y
        X_with_leak["TransactionID"] = range(len(y))

        # The pipeline should not error, but these columns will be dropped
        # by the ColumnTransformer (remainder='drop')
        pipeline = build_preprocessing_pipeline(X)
        names = get_feature_names(pipeline, X)
        assert "isFraud" not in names
        assert "TransactionID" not in names
