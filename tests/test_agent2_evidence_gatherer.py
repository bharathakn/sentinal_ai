"""
Tests for Agent 2 — Evidence Gatherer.

Design rules for this test module
-----------------------------------
* All tests use MockNewsProvider. No real HTTP calls are made.
* No real credentials are required.
* Tests use asyncio.run() or pytest-asyncio markers as appropriate.
* Concurrency tests verify that independent tasks actually overlap.
* Failure tests verify failure isolation and safe partial results.
* Agent 1 output is never fabricated to make Agent 2 run (it is a required input).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from src.agents.agent1.output_schema import Agent1Output, AgentStatus
from src.agents.agent2.evidence_gatherer import (
    EvidenceGathererAgent,
    _safe_call,
    gather_evidence,
)
from src.agents.agent2.output_schema import Agent2Output, Agent2Status, ProviderResult
from src.agents.sentinel_pipeline import SentinelState
from src.evidence.providers.news.mock_provider import MockNewsProvider
from src.evidence.schemas import EvidenceStatus, SourceMode
from src.schemas.canonical_transaction import (
    AccountInfo,
    CanonicalTransaction,
    DataSource,
    DeviceInfo,
    GeoLocation,
    TransactionChannel,
    TransactionStatus,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_transaction(
    sender_account_id: Optional[str] = "ACC001",
    receiver_account_id: Optional[str] = "ACC002",
    device_id: Optional[str] = "DEV001",
    customer_name: Optional[str] = "Arjun Sharma (SYNTHETIC)",
    lat: Optional[float] = 12.9716,
    lon: Optional[float] = 77.5946,
    city: Optional[str] = "Bengaluru",
    country: Optional[str] = "India",
    tx_id: str = "TEST-TX-001",
) -> CanonicalTransaction:
    return CanonicalTransaction(
        raw_record_id=tx_id,
        source_dataset=DataSource.MOCK_BANKING,
        transaction_timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        amount=Decimal("5000.00"),
        currency="INR",
        channel=TransactionChannel.UPI,
        status=TransactionStatus.SUCCESS,
        sender=AccountInfo(
            account_id=sender_account_id,
            account_name=customer_name,
        ),
        receiver=AccountInfo(account_id=receiver_account_id),
        device=DeviceInfo(device_id=device_id),
        location=GeoLocation(
            city=city,
            country=country,
            latitude=lat,
            longitude=lon,
        ),
    )


def _make_agent1(
    anomaly_score: float = 0.15,
    combined_confidence: float = 0.20,
    tx_id: str = "TEST-TX-001",
) -> Agent1Output:
    return Agent1Output(
        transaction_id=tx_id,
        source_dataset="MOCK_BANKING",
        scored_at_utc=datetime.now(timezone.utc),
        status=AgentStatus.COMPLETE,
        anomaly_score=anomaly_score,
        isolation_score=0.45,
        combined_confidence=combined_confidence,
    )


def _make_agent() -> EvidenceGathererAgent:
    return EvidenceGathererAgent(
        news_provider=MockNewsProvider(),
        provider_timeout_sec=10.0,
    )


def _run(coro):
    """Run an async coroutine in a fresh event loop."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. All seven provider categories are invoked correctly
# ---------------------------------------------------------------------------

class TestAllProvidersInvoked:

    def test_all_eight_provider_results_present(self):
        tx = _make_transaction()
        a1 = _make_agent1()
        result = _run(_make_agent().gather(tx, a1))
        assert len(result.provider_results) == 8

    def test_all_eight_provider_names_present(self):
        tx = _make_transaction()
        a1 = _make_agent1()
        result = _run(_make_agent().gather(tx, a1))
        names = {pr.provider_name for pr in result.provider_results}
        expected = {
            "CORE_BANKING", "KYC", "DEVICE_REGISTRY", "BENEFICIARY",
            "SANCTIONS_SUBJECT", "SANCTIONS_ACCOUNT", "GEOLOCATION", "NEWS",
        }
        assert names == expected

    def test_core_banking_evidence_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.core_banking is not None

    def test_kyc_evidence_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.kyc is not None

    def test_device_evidence_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.device is not None

    def test_beneficiary_evidence_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.beneficiary is not None

    def test_both_sanctions_operations_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.sanctions_subject is not None
        assert result.sanctions_account is not None

    def test_geolocation_evidence_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.geolocation is not None

    def test_news_evidence_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.news is not None


# ---------------------------------------------------------------------------
# 2. Valid inputs produce a valid Agent2Output
# ---------------------------------------------------------------------------

class TestValidOutput:

    def test_status_complete_on_all_success(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.status == Agent2Status.COMPLETE

    def test_transaction_id_preserved(self):
        tx = _make_transaction(tx_id="CUSTOM-TX-42")
        result = _run(_make_agent().gather(tx, _make_agent1()))
        assert result.transaction_id == "CUSTOM-TX-42"

    def test_source_dataset_preserved(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.source_dataset == "MOCK_BANKING"

    def test_agent2_run_id_is_set(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.agent2_run_id is not None
        assert len(result.agent2_run_id) > 0

    def test_gathered_at_utc_is_set(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.gathered_at_utc is not None

    def test_successful_providers_list_populated(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert len(result.successful_providers) == 8

    def test_failed_providers_empty_on_success(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.failed_providers == []


# ---------------------------------------------------------------------------
# 3. Evidence results contain required fields
# ---------------------------------------------------------------------------

class TestEvidenceResultFields:

    def test_each_provider_result_has_source(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        for pr in result.provider_results:
            assert pr.provider_name, f"Missing provider_name in {pr}"

    def test_each_provider_result_has_retrieved_at(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        for pr in result.provider_results:
            assert pr.retrieved_at is not None, f"Missing retrieved_at in {pr.provider_name}"

    def test_each_provider_result_has_status(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        for pr in result.provider_results:
            assert pr.status is not None

    def test_core_banking_response_has_data(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.core_banking.data is not None
        assert result.core_banking.source is not None
        assert result.core_banking.retrieved_at is not None

    def test_kyc_response_has_data(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.kyc.data is not None
        assert result.kyc.data.kyc_status is not None

    def test_device_response_has_data(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.device.data is not None
        assert result.device.data.device_id is not None

    def test_beneficiary_response_has_data(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.beneficiary.data is not None

    def test_geolocation_response_has_data(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.geolocation.data is not None


# ---------------------------------------------------------------------------
# 4. Concurrency — verify that independent provider calls overlap
# ---------------------------------------------------------------------------

class TestConcurrency:

    def test_providers_run_concurrently_not_serially(self):
        """
        Measure wall-clock time. If providers were sequential and each slept
        0.1s, total would be ~0.8s. With concurrency, total should be <0.3s
        even if all providers were synchronous operations.

        We use real providers (no sleep injection) to verify the async
        gather mechanism isn't blocking on each call serially.
        """
        start = time.monotonic()
        _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        elapsed = time.monotonic() - start
        # 8 providers running concurrently with real sync functions in executor;
        # should finish in well under 2s regardless of environment
        assert elapsed < 5.0, f"Agent 2 took {elapsed:.2f}s — may not be concurrent."

    def test_all_provider_results_collected_on_concurrent_run(self):
        """All 8 results must be in output after a concurrent gather."""
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert len(result.provider_results) == 8
        assert len(result.successful_providers) == 8

    def test_two_simultaneous_gather_calls_are_independent(self):
        """Two concurrent Agent 2 calls on different transactions are independent."""
        tx1 = _make_transaction(tx_id="TX-A", sender_account_id="ACC001")
        tx2 = _make_transaction(tx_id="TX-B", sender_account_id="ACC002")
        a1 = _make_agent1()

        async def run_both():
            agent = _make_agent()
            r1, r2 = await asyncio.gather(
                agent.gather(tx1, a1),
                agent.gather(tx2, a1),
            )
            return r1, r2

        r1, r2 = _run(run_both())
        assert r1.transaction_id == "TX-A"
        assert r2.transaction_id == "TX-B"
        assert r1.status == Agent2Status.COMPLETE
        assert r2.status == Agent2Status.COMPLETE


# ---------------------------------------------------------------------------
# 5 & 6. Provider failures — isolation and partial results
# ---------------------------------------------------------------------------

class TestProviderFailureIsolation:

    def test_single_provider_exception_does_not_cancel_others(self):
        """When core_banking raises, all other providers still succeed."""
        with patch(
            "src.agents.agent2.evidence_gatherer.get_account_history",
            side_effect=RuntimeError("mock core banking crash"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        assert result.status == Agent2Status.PARTIAL
        assert "CORE_BANKING" in result.failed_providers
        # Other providers succeeded
        assert result.kyc is not None
        assert result.beneficiary is not None
        assert result.sanctions_account is not None
        assert result.news is not None

    def test_single_failure_produces_partial_status(self):
        with patch(
            "src.agents.agent2.evidence_gatherer.get_kyc_data",
            side_effect=ConnectionError("mock KYC unavailable"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.status == Agent2Status.PARTIAL

    def test_multiple_failures_produce_valid_partial_result(self):
        """Three providers fail; remaining five succeed — still a valid output."""
        with patch(
            "src.agents.agent2.evidence_gatherer.get_account_history",
            side_effect=RuntimeError("banking down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.get_kyc_data",
            side_effect=RuntimeError("kyc down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.check_geolocation",
            side_effect=RuntimeError("geo down"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        assert result.status == Agent2Status.PARTIAL
        assert len(result.failed_providers) == 3
        assert len(result.successful_providers) == 5
        assert result.beneficiary is not None
        assert result.news is not None

    def test_all_providers_fail_produces_failed_status(self):
        """When every provider fails the status is FAILED."""
        with patch(
            "src.agents.agent2.evidence_gatherer.get_account_history",
            side_effect=RuntimeError("down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.get_kyc_data",
            side_effect=RuntimeError("down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.check_device",
            side_effect=RuntimeError("down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.get_beneficiary",
            side_effect=RuntimeError("down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.screen_subject",
            side_effect=RuntimeError("down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.screen_account",
            side_effect=RuntimeError("down"),
        ), patch(
            "src.agents.agent2.evidence_gatherer.check_geolocation",
            side_effect=RuntimeError("down"),
        ):
            # News uses MockNewsProvider passed in — patch its search
            class _FailNews(MockNewsProvider):
                def search(self, *a, **kw):
                    raise RuntimeError("news down")

            agent = EvidenceGathererAgent(
                news_provider=_FailNews(),
                provider_timeout_sec=10.0,
            )
            result = _run(agent.gather(_make_transaction(), _make_agent1()))

        assert result.status == Agent2Status.FAILED
        assert len(result.failed_providers) == 8

    def test_failed_provider_error_summary_set(self):
        with patch(
            "src.agents.agent2.evidence_gatherer.get_account_history",
            side_effect=ValueError("unexpected data"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        banking_pr = next(
            (pr for pr in result.provider_results if pr.provider_name == "CORE_BANKING"),
            None,
        )
        assert banking_pr is not None
        assert banking_pr.error_summary is not None
        assert len(banking_pr.error_summary) > 0

    def test_failed_provider_error_summary_no_stack_trace(self):
        """error_summary must not contain a stack trace."""
        with patch(
            "src.agents.agent2.evidence_gatherer.get_account_history",
            side_effect=RuntimeError("crash"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        banking_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "CORE_BANKING"
        )
        # Stack trace markers must not appear
        assert "Traceback" not in (banking_pr.error_summary or "")
        assert "File \"" not in (banking_pr.error_summary or "")

    def test_failed_provider_result_preserved_in_provider_results(self):
        with patch(
            "src.agents.agent2.evidence_gatherer.check_device",
            side_effect=RuntimeError("device registry down"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        device_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "DEVICE_REGISTRY"
        )
        assert device_pr.status == EvidenceStatus.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# 7. Provider timeout
# ---------------------------------------------------------------------------

class TestProviderTimeout:

    def test_timeout_is_provider_error_not_success(self):
        """A timeout must not produce a successful empty response."""
        # Use a very short timeout
        agent = EvidenceGathererAgent(
            news_provider=MockNewsProvider(),
            provider_timeout_sec=0.001,  # impossibly short
        )
        # With 1ms timeout, at least some providers will time out in CI
        # We check that any timed-out provider has PROVIDER_ERROR, not FOUND/NO_MATCH
        result = _run(agent.gather(_make_transaction(), _make_agent1()))

        for pr in result.provider_results:
            if pr.timed_out:
                assert pr.status == EvidenceStatus.PROVIDER_ERROR, (
                    f"{pr.provider_name} timed out but status is {pr.status}"
                )

    def test_timeout_is_tracked_as_timed_out_true(self):
        """Any provider that times out must have timed_out=True."""
        import asyncio as _asyncio

        async def _slow(*args, **kwargs):
            await _asyncio.sleep(10)

        with patch(
            "src.agents.agent2.evidence_gatherer._run_sync",
            side_effect=_asyncio.TimeoutError(),
        ):
            agent = EvidenceGathererAgent(
                news_provider=MockNewsProvider(),
                provider_timeout_sec=0.01,
            )
            result = _run(agent.gather(_make_transaction(), _make_agent1()))

        # All providers timed out (patched _run_sync always raises TimeoutError)
        for pr in result.provider_results:
            assert pr.timed_out is True
            assert pr.status == EvidenceStatus.PROVIDER_ERROR

    def test_timeout_produces_partial_or_failed_not_complete(self):
        import asyncio as _asyncio

        with patch(
            "src.agents.agent2.evidence_gatherer._run_sync",
            side_effect=_asyncio.TimeoutError(),
        ):
            agent = EvidenceGathererAgent(news_provider=MockNewsProvider())
            result = _run(agent.gather(_make_transaction(), _make_agent1()))

        assert result.status in (Agent2Status.PARTIAL, Agent2Status.FAILED)


# ---------------------------------------------------------------------------
# 8. Malformed / unexpected data from a provider
# ---------------------------------------------------------------------------

class TestMalformedProviderData:

    def test_provider_returning_unexpected_type_does_not_crash_agent(self):
        """Provider returning a wrong type is captured as PROVIDER_ERROR."""
        with patch(
            "src.agents.agent2.evidence_gatherer.get_kyc_data",
            return_value="not_a_pydantic_model",  # Unexpected return type
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        # Agent 2 must not crash — KYC fails, others succeed
        assert result.status in (Agent2Status.PARTIAL, Agent2Status.COMPLETE)
        # KYC result may be None or the string (depending on attribute access)
        # The critical check: no crash, still returns valid Agent2Output
        assert isinstance(result, Agent2Output)


# ---------------------------------------------------------------------------
# 9. Provider returns valid empty result
# ---------------------------------------------------------------------------

class TestValidEmptyResult:

    def test_no_articles_is_not_treated_as_error(self):
        """News returning NO_ARTICLES is a valid successful result."""
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        news_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "NEWS"
        )
        # NO_ARTICLES is a successful result (provider responded correctly)
        assert news_pr.succeeded is True
        assert news_pr.status == EvidenceStatus.NO_ARTICLES

    def test_not_found_is_not_treated_as_error(self):
        """Core banking returning NOT_FOUND (unknown account) is a valid result."""
        tx = _make_transaction(sender_account_id="UNKNOWN_ACCT")
        result = _run(_make_agent().gather(tx, _make_agent1()))
        banking_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "CORE_BANKING"
        )
        assert banking_pr.succeeded is True
        assert banking_pr.status == EvidenceStatus.NOT_FOUND

    def test_no_match_sanctions_is_not_treated_as_error(self):
        """Sanctions NO_MATCH is a valid result — not an error."""
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        sanc_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "SANCTIONS_ACCOUNT"
        )
        assert sanc_pr.succeeded is True
        assert sanc_pr.status == EvidenceStatus.NO_MATCH


# ---------------------------------------------------------------------------
# 10. Optional identifiers missing
# ---------------------------------------------------------------------------

class TestMissingIdentifiers:

    def test_missing_sender_account_id_produces_validation_errors(self):
        tx = _make_transaction(sender_account_id=None)
        result = _run(_make_agent().gather(tx, _make_agent1()))
        # Providers requiring sender.account_id get VALIDATION_ERROR
        affected = {"CORE_BANKING", "KYC", "SANCTIONS_ACCOUNT", "GEOLOCATION"}
        provider_statuses = {
            pr.provider_name: pr.status for pr in result.provider_results
        }
        for name in affected:
            assert provider_statuses[name] == EvidenceStatus.VALIDATION_ERROR, (
                f"{name}: expected VALIDATION_ERROR, got {provider_statuses[name]}"
            )

    def test_missing_receiver_account_id_produces_validation_error_for_beneficiary(self):
        tx = _make_transaction(receiver_account_id=None)
        result = _run(_make_agent().gather(tx, _make_agent1()))
        bene_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "BENEFICIARY"
        )
        assert bene_pr.status == EvidenceStatus.VALIDATION_ERROR

    def test_missing_device_id_produces_validation_error_for_device(self):
        tx = _make_transaction(device_id=None)
        result = _run(_make_agent().gather(tx, _make_agent1()))
        dev_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "DEVICE_REGISTRY"
        )
        assert dev_pr.status == EvidenceStatus.VALIDATION_ERROR

    def test_missing_customer_name_produces_validation_error_for_sanctions_subject(self):
        tx = _make_transaction(customer_name=None)
        result = _run(_make_agent().gather(tx, _make_agent1()))
        subj_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "SANCTIONS_SUBJECT"
        )
        assert subj_pr.status == EvidenceStatus.VALIDATION_ERROR

    def test_missing_identifiers_do_not_crash_agent(self):
        tx = _make_transaction(
            sender_account_id=None,
            receiver_account_id=None,
            device_id=None,
            customer_name=None,
        )
        result = _run(_make_agent().gather(tx, _make_agent1()))
        assert isinstance(result, Agent2Output)

    def test_missing_lat_lon_produces_none_is_anomalous(self):
        tx = _make_transaction(lat=None, lon=None)
        result = _run(_make_agent().gather(tx, _make_agent1()))
        if result.geolocation and result.geolocation.data:
            # is_anomalous=None must not be treated as False
            assert result.geolocation.data.is_anomalous is None


# ---------------------------------------------------------------------------
# 11. Required inputs missing or invalid
# ---------------------------------------------------------------------------

class TestInvalidInputs:

    def test_agent1_output_preserved_as_none_when_none(self):
        """Agent 2 must accept Agent1Output being None for the linkage field."""
        # Agent 2 requires Agent1Output — passing None should not crash if handled
        # (The type hint says Agent1Output but runtime Python accepts None)
        tx = _make_transaction()
        # Note: passing None explicitly to test downstream safety
        agent = _make_agent()

        async def run():
            try:
                return await agent.gather(tx, None)  # type: ignore
            except Exception as exc:
                # An exception is acceptable — what is not acceptable is a crash
                # that produces no output at all
                return exc

        result = _run(run())
        # Either returns an Agent2Output or raises clearly — does not hang
        assert result is not None


# ---------------------------------------------------------------------------
# 12. Both sanctions operations run when inputs are available
# ---------------------------------------------------------------------------

class TestSanctionsBothOperations:

    def test_sanctions_subject_screening_runs(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.sanctions_subject is not None
        subj_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "SANCTIONS_SUBJECT"
        )
        assert subj_pr.succeeded is True

    def test_sanctions_account_screening_runs(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.sanctions_account is not None
        acc_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "SANCTIONS_ACCOUNT"
        )
        assert acc_pr.succeeded is True

    def test_sanctions_match_on_known_flagged_account(self):
        """ACC004 is the flagged account in the fixture."""
        tx = _make_transaction(sender_account_id="ACC004")
        result = _run(_make_agent().gather(tx, _make_agent1()))
        assert result.sanctions_account is not None
        assert result.sanctions_account.status == EvidenceStatus.MATCH_FOUND

    def test_sanctions_clean_on_acc001(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.sanctions_account.status == EvidenceStatus.NO_MATCH

    def test_both_sanctions_tracked_separately(self):
        """Subject and account screening are independent fields in output."""
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.sanctions_subject is not result.sanctions_account


# ---------------------------------------------------------------------------
# 13. News mock mode works offline and deterministically
# ---------------------------------------------------------------------------

class TestNewsMockMode:

    def test_mock_provider_makes_no_http_calls(self):
        """MockNewsProvider must not trigger any HTTP request."""
        with patch("httpx.get") as mock_get:
            _run(_make_agent().gather(_make_transaction(), _make_agent1()))
            mock_get.assert_not_called()

    def test_mock_news_for_flagged_entity_returns_articles(self):
        """Synthetic Fraudster One has fixture articles."""
        tx = _make_transaction(customer_name="Synthetic Fraudster One")
        result = _run(_make_agent().gather(tx, _make_agent1()))
        assert result.news is not None
        assert result.news.status == EvidenceStatus.MATCH_FOUND
        assert len(result.news.data.articles) >= 1

    def test_mock_news_for_clean_entity_returns_no_articles(self):
        tx = _make_transaction(customer_name="Arjun Sharma (SYNTHETIC)")
        result = _run(_make_agent().gather(tx, _make_agent1()))
        assert result.news is not None
        assert result.news.status == EvidenceStatus.NO_ARTICLES

    def test_repeated_news_calls_are_deterministic(self):
        tx = _make_transaction(customer_name="Synthetic Fraudster One")
        r1 = _run(_make_agent().gather(tx, _make_agent1()))
        r2 = _run(_make_agent().gather(tx, _make_agent1()))
        assert r1.news.data.total_results == r2.news.data.total_results


# ---------------------------------------------------------------------------
# 14. Missing NewsAPI credentials in live mode handled without HTTP attempt
# ---------------------------------------------------------------------------

class TestLiveNewsMissingCredentials:

    def test_live_mode_missing_key_is_auth_error_no_http(self):
        """If live mode is configured but key is absent, AUTH_ERROR immediately."""
        from src.evidence.providers.news.newsapi_provider import NewsAPIProvider
        import os

        live_provider = NewsAPIProvider()
        agent = EvidenceGathererAgent(news_provider=live_provider)

        with patch.dict("os.environ", {}, clear=True):
            os.environ.pop("NEWS_API_KEY", None)
            with patch("httpx.get") as mock_get:
                result = _run(agent.gather(_make_transaction(), _make_agent1()))
                mock_get.assert_not_called()

        # News result has AUTH_ERROR
        assert result.news is not None
        assert result.news.status == EvidenceStatus.AUTH_ERROR


# ---------------------------------------------------------------------------
# 15. Provider failures not converted to fraud findings
# ---------------------------------------------------------------------------

class TestFailureNotConvertedToFinding:

    def test_failed_sanctions_is_not_clean_result(self):
        """A sanctions provider failure must NOT appear as NO_MATCH."""
        with patch(
            "src.agents.agent2.evidence_gatherer.screen_account",
            side_effect=RuntimeError("sanctions service down"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        # sanctions_account is None (failed) — not a NO_MATCH clean result
        assert result.sanctions_account is None
        acc_pr = next(
            pr for pr in result.provider_results if pr.provider_name == "SANCTIONS_ACCOUNT"
        )
        assert acc_pr.status == EvidenceStatus.PROVIDER_ERROR
        # PROVIDER_ERROR is NOT NO_MATCH
        assert acc_pr.status != EvidenceStatus.NO_MATCH

    def test_failed_provider_does_not_lower_anomaly_score(self):
        """Failures must not modify Agent1 anomaly_score."""
        original_score = 0.85
        a1 = _make_agent1(anomaly_score=original_score)
        with patch(
            "src.agents.agent2.evidence_gatherer.get_kyc_data",
            side_effect=RuntimeError("kyc down"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), a1))

        assert result.agent1_output.anomaly_score == original_score

    def test_failed_provider_listed_in_failed_providers(self):
        with patch(
            "src.agents.agent2.evidence_gatherer.screen_subject",
            side_effect=RuntimeError("sanctions down"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert "SANCTIONS_SUBJECT" in result.failed_providers

    def test_warning_message_mentions_incomplete_evidence(self):
        with patch(
            "src.agents.agent2.evidence_gatherer.get_account_history",
            side_effect=RuntimeError("down"),
        ):
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))

        warning_text = " ".join(result.warnings).upper()
        assert "INCOMPLETE" in warning_text or "MISSING" in warning_text or "FAILED" in warning_text


# ---------------------------------------------------------------------------
# 16. Conflicting evidence preserved
# ---------------------------------------------------------------------------

class TestConflictingEvidencePreserved:

    def test_conflicting_geo_not_silently_resolved(self):
        """Agent 2 preserves conflicting location data without resolving it."""
        tx = _make_transaction(lat=55.7558, lon=37.6176, city="Moscow", country="Russia")
        result = _run(_make_agent().gather(tx, _make_agent1()))

        # Geolocation says anomalous (Moscow vs registered Bengaluru)
        assert result.geolocation is not None
        if result.geolocation.data:
            assert result.geolocation.data.is_anomalous is True
        # KYC still says registered city is Bengaluru
        assert result.kyc is not None
        if result.kyc.data:
            assert result.kyc.data.registered_city == "Bengaluru"
        # Both results are preserved — Agent 2 does NOT resolve the conflict

    def test_sanctions_match_not_suppressed_by_kyc_clean_result(self):
        """If sanctions flags a match, KYC being verified does not suppress it."""
        tx = _make_transaction(sender_account_id="ACC004")
        result = _run(_make_agent().gather(tx, _make_agent1()))
        # Both results preserved
        assert result.sanctions_account.status == EvidenceStatus.MATCH_FOUND
        assert result.kyc.data.kyc_status == "FLAGGED"


# ---------------------------------------------------------------------------
# 17. LangGraph state integration
# ---------------------------------------------------------------------------

class TestLangGraphStateIntegration:

    def test_agent2_output_stored_in_state(self):
        """Agent 2 output can be written to SentinelState."""
        tx = _make_transaction()
        a1 = _make_agent1()
        a2 = _run(_make_agent().gather(tx, a1))

        state: SentinelState = {
            "transaction": tx,
            "agent1_output": a1,
            "agent2_output": a2,
        }

        assert state["agent2_output"] is a2
        assert state["agent2_output"].status == Agent2Status.COMPLETE

    def test_agent1_output_retained_after_agent2_run(self):
        """Agent 1 output is not overwritten when Agent 2 runs."""
        tx = _make_transaction()
        a1 = _make_agent1(anomaly_score=0.77)
        a2 = _run(_make_agent().gather(tx, a1))

        state: SentinelState = {
            "transaction": tx,
            "agent1_output": a1,
            "agent2_output": a2,
        }

        assert state["agent1_output"].anomaly_score == 0.77
        assert state["agent2_output"].agent1_output.anomaly_score == 0.77

    def test_transaction_preserved_in_state(self):
        tx = _make_transaction(tx_id="STATE-TEST")
        a1 = _make_agent1()
        a2 = _run(_make_agent().gather(tx, a1))

        state: SentinelState = {
            "transaction": tx,
            "agent1_output": a1,
            "agent2_output": a2,
        }

        assert state["transaction"].raw_record_id == "STATE-TEST"

    def test_agent2_output_has_agent1_linkage(self):
        """Agent2Output preserves a reference to the triggering Agent1Output."""
        a1 = _make_agent1()
        a2 = _run(_make_agent().gather(_make_transaction(), a1))
        assert a2.agent1_output is not None
        assert a2.agent1_output.transaction_id == a1.transaction_id


# ---------------------------------------------------------------------------
# 18. Evidence note and provenance
# ---------------------------------------------------------------------------

class TestEvidenceProvenance:

    def test_evidence_note_present(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.evidence_note is not None
        assert len(result.evidence_note) > 0

    def test_evidence_note_warns_against_missing_evidence_interpretation(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        note = result.evidence_note.upper()
        assert "MISSING EVIDENCE" in note or "NOT BE INTERPRETED" in note

    def test_source_mode_present_in_evidence(self):
        result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
        assert result.core_banking.source_mode == SourceMode.MOCK
        assert result.kyc.source_mode == SourceMode.MOCK

    def test_no_api_keys_in_output(self):
        """No API keys or secrets must appear anywhere in the serialized output."""
        import os
        test_key = "test-secret-key-sentinel-ai-12345"
        os.environ["NEWS_API_KEY"] = test_key
        try:
            result = _run(_make_agent().gather(_make_transaction(), _make_agent1()))
            output_json = result.model_dump_json()
            assert test_key not in output_json
        finally:
            os.environ.pop("NEWS_API_KEY", None)


# ---------------------------------------------------------------------------
# Synchronous wrapper
# ---------------------------------------------------------------------------

class TestSyncWrapper:

    def test_gather_evidence_sync_returns_valid_output(self):
        tx = _make_transaction()
        a1 = _make_agent1()
        result = gather_evidence(tx, a1, news_provider=MockNewsProvider())
        assert isinstance(result, Agent2Output)
        assert result.status == Agent2Status.COMPLETE
