"""
Sentinel AI — Phase 9.5 tests: investigation data coherence.

Covers:
  - Synthetic India generator v2: validation, determinism, label isolation,
    real network structure for network scenarios
  - IndiaSyntheticStore: point-in-time evidence, label firewall, devices,
    known beneficiaries
  - Evidence providers on the India backend
  - India behavioural model: train / serve parity, routing in Agent 1,
    fallback when the model is missing
  - Label firewall + case identity (new_case_state)
  - Investigator sequential runner (with injected fakes)

A small dataset is generated once into a temporary directory; no local data
files, database or network are required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.data.synthetic_india_generator import SyntheticIndiaDatasetGenerator
from src.data.validate_synthetic_dataset import SyntheticDatasetValidator
from src.evidence import data_store
from src.evidence.data_store import FixtureStore, IndiaSyntheticStore, get_store, set_store
from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

SMALL = dict(seed=11, num_transactions=900, num_customers=150, num_accounts=190)


@pytest.fixture(scope="module")
def small_data(tmp_path_factory) -> tuple[Path, dict]:
    out = tmp_path_factory.mktemp("india_small")
    data = SyntheticIndiaDatasetGenerator(**SMALL).generate_all()
    for name, df in data.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return out, data


@pytest.fixture(scope="module")
def india_store(small_data) -> IndiaSyntheticStore:
    return IndiaSyntheticStore(small_data[0])


@pytest.fixture()
def use_india_store(india_store):
    set_store(india_store)
    yield india_store
    set_store(None)


def _tx(data: dict, idx: int):
    return IndiaSyntheticAdapter.from_row(data["transactions_features"].iloc[idx].to_dict())


# ---------------------------------------------------------------------------
# Generator v2
# ---------------------------------------------------------------------------

class TestGeneratorV2:
    def test_validation_passes(self, small_data):
        res = SyntheticDatasetValidator(small_data[1]).validate_all()
        assert res["passed"], res["errors"]
        assert res["checks"]["7_behavioural_consistency"] == "PASSED"

    def test_deterministic(self, small_data):
        again = SyntheticIndiaDatasetGenerator(**SMALL).generate_all()
        for name in ("transactions_features", "beneficiaries", "devices"):
            pd.testing.assert_frame_equal(again[name], small_data[1][name])

    def test_transaction_count(self, small_data):
        assert len(small_data[1]["transactions_features"]) == SMALL["num_transactions"]

    def test_labels_only_in_targets(self, small_data):
        d = small_data[1]
        forbidden = {"is_fraud", "risk_label", "scenario_id", "pattern_id"}
        assert not forbidden & set(d["transactions_features"].columns)
        assert not forbidden & set(d["graph_edges"].columns)
        assert forbidden <= set(d["transactions_targets"].columns)

    def test_layering_patterns_are_chains(self, small_data):
        d = small_data[1]
        m = d["transactions_features"].merge(d["transactions_targets"], on="transaction_id")
        lay = m[m["scenario_id"] == "SCENARIO_7_LAYERING_NETWORK"]
        assert len(lay)
        for _, g in lay.groupby("pattern_id"):
            g = g.sort_values("timestamp")
            if len(g) < 2:
                continue
            # each hop's sender is the previous hop's receiver
            assert list(g["sender_account_id"])[1:] == list(g["receiver_account_id"])[:-1]

    def test_mule_patterns_fan_in_then_out(self, small_data):
        d = small_data[1]
        m = d["transactions_features"].merge(d["transactions_targets"], on="transaction_id")
        for _, g in m[m["scenario_id"] == "SCENARIO_8_MULE_PASS_THROUGH"].groupby("pattern_id"):
            mule = g["receiver_account_id"].mode().iloc[0]
            ins = g[g["receiver_account_id"] == mule]
            outs = g[g["sender_account_id"] == mule]
            if len(outs):
                assert ins["timestamp"].min() < outs["timestamp"].min()
                assert ins["sender_account_id"].nunique() >= 2
                break
        else:
            pytest.skip("no complete mule pattern in small sample")

    def test_transaction_ids_chronological(self, small_data):
        f = small_data[1]["transactions_features"]
        assert pd.to_datetime(f["timestamp"], utc=True).is_monotonic_increasing


# ---------------------------------------------------------------------------
# India evidence store
# ---------------------------------------------------------------------------

class TestIndiaStore:
    def test_history_strictly_before_as_of(self, small_data, india_store):
        f = small_data[1]["transactions_features"]
        row = f.iloc[len(f) // 2]
        as_of = datetime.fromisoformat(row["timestamp"])
        hist = india_store.get_transaction_history(row["sender_account_id"], as_of)
        assert all(h["timestamp"] < as_of for h in hist)
        assert row["transaction_id"] not in {h["tx_id"] for h in hist}

    def test_no_as_of_returns_history(self, small_data, india_store):
        acc = small_data[1]["transactions_features"]["sender_account_id"].iloc[0]
        assert india_store.get_transaction_history(acc)

    def test_label_account_type_masked(self, small_data, india_store):
        acc = small_data[1]["accounts"]
        mules = acc[acc["account_type"] == "MULE_SUSPECT"]["account_id"]
        assert len(mules) > 0
        for a in mules:
            assert india_store.get_account(a)["account_type"] is None
        normal = acc[acc["account_type"] == "SAVINGS"]["account_id"].iloc[0]
        assert india_store.get_account(normal)["account_type"] == "SAVINGS"

    def test_does_not_need_targets_file(self, small_data, tmp_path):
        for name in ("customers", "accounts", "devices", "beneficiaries", "transactions_features"):
            (tmp_path / f"{name}.csv").write_bytes((small_data[0] / f"{name}.csv").read_bytes())
        store = IndiaSyntheticStore(tmp_path)  # no transactions_targets.csv present
        acc = small_data[1]["accounts"]["account_id"].iloc[0]
        assert store.get_account(acc) is not None

    def test_account_profile(self, small_data, india_store):
        acc = small_data[1]["accounts"].iloc[0]
        p = india_store.get_account(acc["account_id"])
        assert p["customer_id"] == acc["customer_id"]
        assert p["customer_name"].endswith("(SYNTHETIC)")
        assert p["registered_latitude"] is not None
        assert india_store.get_account("NOPE") is None

    def test_known_beneficiaries_match_flag(self, small_data, india_store):
        f = small_data[1]["transactions_features"]
        checked = 0
        for _, r in f.sample(60, random_state=1).iterrows():
            stats = india_store.get_account_stats(r["sender_account_id"], datetime.fromisoformat(r["timestamp"]))
            known = r["receiver_account_id"] in stats["known_beneficiaries"]
            if r["time_since_beneficiary_added_min"] >= 30 * 1440:
                assert known  # established registered payee
                checked += 1
        assert checked

    def test_device_registration_matches_new_device_flag(self, small_data, india_store):
        f = small_data[1]["transactions_features"]
        new = f[f["is_new_device"] == 1]
        reg = [india_store.is_device_registered_to_account(r.sender_account_id, r.device_id)
               for r in f[f["is_new_device"] == 0].itertuples()]
        assert all(reg)
        assert len(new) > 0

    def test_device_associated_accounts_point_in_time(self, small_data, india_store):
        f = small_data[1]["transactions_features"]
        dev = f["device_id"].value_counts().index[0]
        first = datetime.fromisoformat(f[f["device_id"] == dev]["timestamp"].min())
        early = india_store.get_device(dev, as_of=first)
        late = india_store.get_device(dev)
        assert set(early["associated_accounts"]) <= set(late["associated_accounts"])

    def test_fraud_flag_unknown(self, india_store):
        assert india_store.is_fraud_flagged("ANY") is None

    def test_backend_selection(self, monkeypatch):
        set_store(None)
        monkeypatch.setenv("SENTINEL_EVIDENCE_BACKEND", "fixture")
        assert isinstance(get_store(), FixtureStore)
        set_store(None)
        monkeypatch.setenv("SENTINEL_EVIDENCE_BACKEND", "bogus")
        with pytest.raises(ValueError):
            get_store()
        set_store(None)


class TestProvidersOnIndiaBackend:
    def test_sources_are_labelled(self, small_data, use_india_store):
        from src.evidence.providers import get_account_history, get_kyc_data

        acc = small_data[1]["accounts"]["account_id"].iloc[0]
        assert get_kyc_data(acc).source == "SYNTHETIC_INDIA_KYC"
        r = get_account_history(acc)
        assert r.source == "SYNTHETIC_INDIA_CORE_BANKING"
        assert "SYNTHETIC" in r.data.synthetic_notice

    def test_beneficiary_fraud_flag_warning(self, small_data, use_india_store):
        from src.evidence.providers import get_beneficiary

        acc = small_data[1]["accounts"]["account_id"].iloc[1]
        r = get_beneficiary(acc)
        assert r.data.previous_fraud_flag is False
        assert any("not determinable" in w for w in r.warnings)

    def test_geolocation_matches_dataset_distance(self, small_data, use_india_store):
        from src.evidence.providers.geolocation import check_geolocation

        row = small_data[1]["transactions_features"].iloc[5]
        g = check_geolocation(row["sender_account_id"], row["tx_lat"], row["tx_long"])
        assert g.data.distance_km == pytest.approx(row["distance_from_home_km"], abs=1.0)

    def test_agent2_complete_with_kyc_name_screening(self, small_data, use_india_store):
        from src.agents.agent1.output_schema import Agent1Output, AgentStatus
        from src.agents.agent2.evidence_gatherer import gather_evidence

        tx = _tx(small_data[1], 10)
        a1 = Agent1Output(scored_at_utc=datetime.now(timezone.utc), status=AgentStatus.COMPLETE)
        out = gather_evidence(tx, a1)
        assert out.status.value == "COMPLETE", out.failed_providers
        assert out.sanctions_subject is not None


# ---------------------------------------------------------------------------
# India behavioural model + Agent 1 routing
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def india_model(small_data, tmp_path_factory) -> Path:
    from src.ml.india_behaviour_model import train

    out = tmp_path_factory.mktemp("india_model")
    train(small_data[0], out, seed=3)
    return out


class TestIndiaModel:
    def test_feature_parity(self, small_data):
        from src.ml.india_behaviour_model import FEATURES, extract_features

        feats = extract_features(_tx(small_data[1], 0))
        assert list(feats) == FEATURES

    def test_features_ignore_labels(self, small_data):
        from src.ml.india_behaviour_model import extract_features

        d = small_data[1]
        row = d["transactions_features"].iloc[3].to_dict()
        with_labels = {**row, **d["transactions_targets"].iloc[3].to_dict()}
        a = extract_features(IndiaSyntheticAdapter.from_row(row))
        b = extract_features(IndiaSyntheticAdapter.from_row(with_labels))
        assert a == pytest.approx(b, nan_ok=True)

    def test_excluded_agent4_signals(self):
        from src.ml.india_behaviour_model import FEATURES

        for f in ("is_new_device", "is_new_beneficiary", "distance_from_home_km",
                  "time_since_beneficiary_added_min"):
            assert f not in FEATURES

    def test_metadata_and_caveat(self, india_model):
        import json

        meta = json.loads((india_model / "metadata.json").read_text())
        assert "SYNTHETIC" in meta["caveat"]
        assert set(meta["metrics"]) == {"xgboost", "isolation_forest"}

    def test_scorer(self, small_data, india_model):
        from src.ml.india_behaviour_model import IndiaBehaviourScorer

        r = IndiaBehaviourScorer(india_model).score(_tx(small_data[1], 7))
        assert 0.0 <= r["fraud_probability"] <= 1.0
        assert r["shap"] is not None

    def test_feature_mismatch_rejected(self, india_model, tmp_path):
        import json
        import shutil

        from src.ml.india_behaviour_model import IndiaBehaviourScorer

        for p in india_model.iterdir():
            shutil.copy(p, tmp_path / p.name)
        meta = json.loads((tmp_path / "metadata.json").read_text())
        meta["features"] = meta["features"][:-1]
        (tmp_path / "metadata.json").write_text(json.dumps(meta))
        with pytest.raises(ValueError):
            IndiaBehaviourScorer(tmp_path)

    def test_agent1_routes_india_to_native_model(self, small_data, india_model):
        from src.agents.agent1 import AnomalyDetectorAgent

        out = AnomalyDetectorAgent(india_model_dir=str(india_model)).score(_tx(small_data[1], 7))
        assert out.feature_mapping.scoring_mode.value == "INDIA_NATIVE"
        assert out.status.value in ("COMPLETE", "PARTIAL")
        assert out.combined_confidence is not None
        assert out.top_deviation_features

    def test_agent1_falls_back_when_model_missing(self, small_data, tmp_path):
        from src.agents.agent1 import AnomalyDetectorAgent

        out = AnomalyDetectorAgent(india_model_dir=str(tmp_path / "none")).score(_tx(small_data[1], 7))
        assert out.feature_mapping.scoring_mode.value == "CANONICAL_MAPPED"
        assert any("India behaviour model unavailable" in w for w in out.warnings)


# ---------------------------------------------------------------------------
# Label firewall + case identity + runner
# ---------------------------------------------------------------------------

class TestCaseStateAndFirewall:
    def test_strip_ground_truth(self, small_data):
        from src.agents.sentinel_pipeline import strip_ground_truth

        d = small_data[1]
        row = {**d["transactions_features"].iloc[0].to_dict(), **d["transactions_targets"].iloc[0].to_dict()}
        tx = IndiaSyntheticAdapter.from_row(row)
        assert tx.metadata.risk_label is not None  # adapter does carry labels
        clean = strip_ground_truth(tx)
        assert clean.is_fraud is None
        assert clean.metadata.risk_label is None and clean.metadata.scenario_id is None
        assert clean.amount == tx.amount and clean.raw_record_id == tx.raw_record_id

    def test_new_case_state(self, small_data):
        from src.agents.sentinel_pipeline import new_case_state

        d = small_data[1]
        row = {**d["transactions_features"].iloc[0].to_dict(), **d["transactions_targets"].iloc[0].to_dict()}
        s1 = new_case_state(IndiaSyntheticAdapter.from_row(row))
        s2 = new_case_state(IndiaSyntheticAdapter.from_row(row))
        assert s1["case_id"].startswith("CASE-") and s1["case_id"] != s2["case_id"]
        assert s1["case_created_at_utc"].tzinfo is not None
        assert s1["transaction"].metadata.risk_label is None

    def test_explicit_case_id(self, small_data):
        from src.agents.sentinel_pipeline import new_case_state

        s = new_case_state(_tx(small_data[1], 0), case_id="CASE-X")
        assert s["case_id"] == "CASE-X"

    def test_investigator_runs_agents_in_order(self, small_data, use_india_store):
        from src.agents.agent1.output_schema import Agent1Output, AgentStatus
        from src.agents.agent3.output_schema import Agent3Output, Agent3Status
        from src.agents.investigation import Investigator

        seen = []

        class FakeA1:
            def score(self, tx):
                seen.append(("a1", tx.metadata.risk_label))
                return Agent1Output(scored_at_utc=datetime.now(timezone.utc), status=AgentStatus.COMPLETE,
                                    anomaly_score=0.2, isolation_score=0.4, combined_confidence=0.2)

        class FakeA3:
            def __call__(self, state):
                seen.append(("a3", "agent2_output" in state))
                return {**state, "agent3_output": Agent3Output(status=Agent3Status.COMPLETE)}

        d = small_data[1]
        row = {**d["transactions_features"].iloc[20].to_dict(), **d["transactions_targets"].iloc[20].to_dict()}
        inv = Investigator(agent1=FakeA1(), agent3=FakeA3())
        state = inv.investigate(IndiaSyntheticAdapter.from_row(row), case_id="CASE-T")
        assert seen == [("a1", None), ("a3", True)]  # labels stripped before Agent 1
        assert state["case_id"] == "CASE-T"
        assert state["agent4_output"].status.value == "COMPLETE"
        # Agent 5 runs last and writes a draft report (template in tests)
        r = state["agent5_output"]
        assert r.case_id == "CASE-T" and r.generator.value == "TEMPLATE"
        assert r.validation_status == "NOT_VALIDATED"
        assert Investigator(agent1=FakeA1(), agent3=FakeA3(), generate_report=False).agent5 is None
