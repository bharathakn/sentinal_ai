"""Deployment readiness: the service must start where only the India
artifacts exist (hosted deployments do not ship the IEEE-CIS models)."""

from pathlib import Path

import pandas as pd
import pytest

from src.agents.agent1.anomaly_detector import AnomalyDetectorAgent
from src.agents.agent1.output_schema import AgentStatus, ScoringMode
from src.ml.india_behaviour_model import DEFAULT_MODEL_DIR
from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

DATA = Path("dataset/processed/custom_india/transactions_features.csv")
MISSING = "/nonexistent/sentinel-models"


def test_missing_ieee_models_fail_fast_by_default(monkeypatch):
    monkeypatch.delenv("SENTINEL_REQUIRE_IEEE_MODELS", raising=False)
    with pytest.raises(FileNotFoundError):
        AnomalyDetectorAgent(xgb_model_dir=MISSING, if_model_dir=MISSING, use_india_model=False)


@pytest.mark.parametrize("via_env", [True, False])
def test_ieee_models_optional(monkeypatch, via_env):
    if via_env:
        monkeypatch.setenv("SENTINEL_REQUIRE_IEEE_MODELS", "false")
        agent = AnomalyDetectorAgent(xgb_model_dir=MISSING, if_model_dir=MISSING, use_india_model=False)
    else:
        agent = AnomalyDetectorAgent(xgb_model_dir=MISSING, if_model_dir=MISSING,
                                     use_india_model=False, require_ieee_models=False)
    assert not agent.xgb_available and not agent.if_available
    out = agent.score_raw({"TransactionAmt": 100.0}, transaction_id="T1")
    assert out.status == AgentStatus.FAILED  # structured failure, no exception


@pytest.mark.skipif(not (DATA.exists() and Path(DEFAULT_MODEL_DIR).exists()),
                    reason="India dataset / model not built")
def test_india_scoring_without_ieee_models():
    agent = AnomalyDetectorAgent(xgb_model_dir=MISSING, if_model_dir=MISSING, require_ieee_models=False)
    row = pd.read_csv(DATA, nrows=1).to_dict("records")[0]
    out = agent.score(IndiaSyntheticAdapter.from_row(row))
    assert out.status == AgentStatus.COMPLETE
    assert out.feature_mapping.scoring_mode == ScoringMode.INDIA_NATIVE
