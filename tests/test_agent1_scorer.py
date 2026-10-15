"""
Tests for src/ml/agent1_scorer.py (Agent1Scorer).

Verifies:
- Agent1Scorer loads both XGBoost and Isolation Forest predictors
- score() executes on a CanonicalTransaction and returns structured dict
- Output keys are properly segregated (xgboost vs iforest)
- Combined disclaimer note is present
- score_raw() accepts raw feature dicts
- Custom threshold overrides work for both models
- mapping_info returns valid description dict
- Safe error handling when model artifacts are missing
"""

from __future__ import annotations

from decimal import Decimal
import pytest

from src.ml.agent1_scorer import Agent1Scorer
from src.schemas.canonical_transaction import CanonicalTransaction
from src.schemas.adapters.ieee_cis_adapter import IEEECISAdapter


class TestAgent1ScorerInitialization:
    def test_default_init_succeeds(self):
        scorer = Agent1Scorer()
        assert scorer._xgb is not None
        assert scorer._iforest is not None

    def test_missing_model_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Agent1Scorer(xgb_model_dir=str(tmp_path / "nonexistent"))


class TestAgent1ScorerScore:
    @pytest.fixture
    def scorer(self):
        return Agent1Scorer()

    @pytest.fixture
    def canonical_tx(self):
        raw_row = {
            "TransactionID": 2987000,
            "TransactionAmt": 150.0,
            "TransactionDT": 86400,
            "ProductCD": "W",
            "card4": "visa",
            "card6": "credit",
            "addr1": 315.0,
            "addr2": 87.0,
            "P_emaildomain": "gmail.com",
            "R_emaildomain": "yahoo.com",
        }
        return IEEECISAdapter.from_row(raw_row)

    def test_score_required_top_level_keys(self, scorer, canonical_tx):
        result = scorer.score(canonical_tx)
        assert "raw_record_id" in result
        assert "source_dataset" in result
        assert "xgboost" in result
        assert "iforest" in result
        assert "combined_note" in result
        assert "mapping_summary" in result

    def test_score_provenance(self, scorer, canonical_tx):
        result = scorer.score(canonical_tx)
        assert result["raw_record_id"] == "2987000"
        assert result["source_dataset"] == "IEEE_CIS"

    def test_score_xgboost_structure(self, scorer, canonical_tx):
        result = scorer.score(canonical_tx)
        xgb = result["xgboost"]
        assert "fraud_probability" in xgb
        assert 0.0 <= xgb["fraud_probability"] <= 1.0
        assert isinstance(xgb["is_fraud_predicted"], bool)
        assert "threshold_used" in xgb
        assert "model_version" in xgb
        assert "note" in xgb

    def test_score_iforest_structure(self, scorer, canonical_tx):
        result = scorer.score(canonical_tx)
        iforest = result["iforest"]
        assert "anomaly_score" in iforest
        assert isinstance(iforest["anomaly_score"], float)
        assert isinstance(iforest["is_anomaly"], bool)
        assert "threshold_used" in iforest
        assert "model_version" in iforest
        assert "score_note" in iforest

    def test_score_combined_disclaimer(self, scorer, canonical_tx):
        result = scorer.score(canonical_tx)
        note = result["combined_note"]
        assert "Do NOT sum" in note or "independent" in note

    def test_score_custom_threshold_override(self, canonical_tx):
        scorer_custom = Agent1Scorer(xgb_threshold=0.99, if_threshold=0.99)
        result = scorer_custom.score(canonical_tx)
        assert result["xgboost"]["threshold_used"] == 0.99
        assert result["iforest"]["threshold_used"] == 0.99


class TestAgent1ScorerScoreRaw:
    @pytest.fixture
    def scorer(self):
        return Agent1Scorer()

    def test_score_raw_valid(self, scorer):
        raw_features = {"TransactionAmt": 250.0, "card4": "mastercard"}
        result = scorer.score_raw(raw_features)
        assert "xgboost" in result
        assert "iforest" in result
        assert "combined_note" in result
        assert result["raw_record_id"] is None
        assert result["source_dataset"] is None


class TestAgent1ScorerMappingInfo:
    def test_mapping_info_property(self):
        scorer = Agent1Scorer()
        info = scorer.mapping_info
        assert "mapped_columns" in info
        assert "total_ieee_cis_features" in info
        assert info["total_ieee_cis_features"] == 432
