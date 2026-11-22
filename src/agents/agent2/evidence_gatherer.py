"""
Sentinel AI — Agent 2: Evidence Gatherer.

Responsibility
--------------
Accept a CanonicalTransaction and Agent1Output, query all seven evidence
provider categories concurrently using asyncio, and aggregate the results
into a structured, validated Agent2Output.

Design rules
------------
* All seven provider categories are called.
* Independent provider calls execute concurrently (asyncio.gather).
* Synchronous provider functions run in a thread pool executor to avoid
  blocking the event loop.
* One provider timeout or failure does NOT cancel other providers.
* Failed providers are preserved in the output — never silently dropped
  or converted into clean/negative findings.
* A timeout is represented as PROVIDER_ERROR with timed_out=True,
  NOT as a successful empty response.
* Agent 2 does not produce, modify, or interpret risk scores.
* No credentials, stack traces, or API keys appear in the output.

LangGraph integration
---------------------
LangGraph is not yet installed. Agent 2 is implemented as a standalone
async callable. When LangGraph is installed, wrap `gather()` as a node
via `SentinelPipeline`. The state TypedDict in sentinel_pipeline.py is
already LangGraph-compatible.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
import contextvars
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

from ...evidence.config import get_news_provider_mode, NewsProviderMode
from ...evidence.providers import (
    check_device,
    check_geolocation,
    get_account_history,
    get_beneficiary,
    get_kyc_data,
    screen_account,
    screen_subject,
    MockNewsProvider,
    NewsAPIProvider,
    BaseNewsProvider,
)
from ...evidence.schemas import EvidenceStatus
from ...schemas.canonical_transaction import CanonicalTransaction
from ..agent1.output_schema import Agent1Output
from .output_schema import Agent2Output, Agent2Status, ProviderResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum time (seconds) to wait for a single provider.
_PROVIDER_TIMEOUT_SEC = 15.0

# Shared thread pool for running synchronous provider functions.
# Bounded to avoid unbounded parallelism from nested event loops.
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent2-evidence")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _run_sync(fn: Callable, *args, timeout: float = _PROVIDER_TIMEOUT_SEC) -> Any:
    """Run a synchronous provider function in the thread pool with a timeout.

    Returns the result or raises asyncio.TimeoutError on timeout,
    or any exception raised by the provider function.
    """
    loop = asyncio.get_event_loop()
    # copy_context: providers must see the evidence store of the current investigation.
    fut = loop.run_in_executor(_executor, contextvars.copy_context().run, fn, *args)
    return await asyncio.wait_for(fut, timeout=timeout)


async def _safe_call(
    provider_name: str,
    fn: Callable,
    *args,
    timeout: float = _PROVIDER_TIMEOUT_SEC,
) -> tuple[Any, ProviderResult]:
    """Execute a provider call safely, capturing all failure modes.

    Returns (result_or_None, ProviderResult).
    - On success: result is the provider's EvidenceResponse.
    - On timeout: result is None, ProviderResult.timed_out=True.
    - On any other exception: result is None, ProviderResult.error_summary set.

    Never raises. Never converts failure into a clean finding.
    """
    try:
        result = await _run_sync(fn, *args, timeout=timeout)
        retrieved_at = getattr(result, "retrieved_at", datetime.now(timezone.utc))
        pr = ProviderResult(
            provider_name=provider_name,
            status=result.status,
            retrieved_at=retrieved_at,
            timed_out=False,
        )
        return result, pr
    except asyncio.TimeoutError:
        logger.warning("Provider '%s' timed out after %.1fs.", provider_name, timeout)
        pr = ProviderResult(
            provider_name=provider_name,
            status=EvidenceStatus.PROVIDER_ERROR,
            retrieved_at=datetime.now(timezone.utc),
            timed_out=True,
            error_summary=f"Provider '{provider_name}' timed out after {timeout:.0f}s.",
        )
        return None, pr
    except Exception as exc:
        # Sanitize: do not expose stack traces or credentials in output
        safe_msg = f"Provider '{provider_name}' raised {type(exc).__name__}."
        logger.warning("%s: %s", safe_msg, exc)
        pr = ProviderResult(
            provider_name=provider_name,
            status=EvidenceStatus.PROVIDER_ERROR,
            retrieved_at=datetime.now(timezone.utc),
            timed_out=False,
            error_summary=safe_msg,
        )
        return None, pr


def _get_news_provider() -> BaseNewsProvider:
    """Select the news provider from configuration. Explicit — no silent fallback."""
    mode = get_news_provider_mode()
    if mode == NewsProviderMode.LIVE:
        return NewsAPIProvider()
    return MockNewsProvider()


# ---------------------------------------------------------------------------
# Agent 2 main class
# ---------------------------------------------------------------------------

class EvidenceGathererAgent:
    """Agent 2 — Evidence Gatherer.

    Accepts a CanonicalTransaction and Agent1Output, concurrently queries
    all seven evidence provider categories, and returns a structured
    Agent2Output.

    Usage
    -----
    agent2 = EvidenceGathererAgent()
    result = await agent2.gather(transaction, agent1_output)
    """

    def __init__(
        self,
        provider_timeout_sec: float = _PROVIDER_TIMEOUT_SEC,
        news_provider: Optional[BaseNewsProvider] = None,
    ) -> None:
        """Construct the agent.

        Parameters
        ----------
        provider_timeout_sec : Per-provider timeout in seconds.
        news_provider        : Override news provider (for testing). If None,
                               the configured provider is used.
        """
        self._timeout = provider_timeout_sec
        self._news_provider_override = news_provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def gather(
        self,
        transaction: CanonicalTransaction,
        agent1_output: Agent1Output,
    ) -> Agent2Output:
        """Gather evidence for a transaction concurrently.

        Parameters
        ----------
        transaction   : Validated canonical transaction.
        agent1_output : Anomaly Detector output from Agent 1.

        Returns
        -------
        Agent2Output — always returns, never raises.
        """
        tx_id = transaction.raw_record_id
        source_dataset = str(transaction.source_dataset) if transaction.source_dataset else None

        # Extract identifiers from the canonical transaction
        sender_account_id = transaction.sender.account_id
        receiver_account_id = transaction.receiver.account_id
        device_id = transaction.device.device_id
        customer_name = transaction.sender.account_name  # For sanctions subject screening
        # Point-in-time cutoff: evidence history must precede the transaction.
        as_of = transaction.timestamp
        name_notes: list[str] = []

        tx_lat = transaction.location.latitude
        tx_lon = transaction.location.longitude
        tx_city = transaction.location.city
        tx_country = transaction.location.country

        news_provider = self._news_provider_override or _get_news_provider()

        # Build news query from available identifiers
        news_query = customer_name or sender_account_id or tx_id

        # ------------------------------------------------------------------
        # Launch all independent provider calls concurrently
        # ------------------------------------------------------------------

        tasks: dict[str, asyncio.Task] = {}

        async def make_task(name: str, fn: Callable, *args):
            return await _safe_call(name, fn, *args, timeout=self._timeout)

        # Core Banking — sender account history
        t_banking = asyncio.ensure_future(
            make_task("CORE_BANKING", get_account_history, sender_account_id, as_of)
            if sender_account_id else _missing_id_result("CORE_BANKING", "sender.account_id")
        )

        # KYC — sender profile
        t_kyc = asyncio.ensure_future(
            make_task("KYC", get_kyc_data, sender_account_id)
            if sender_account_id else _missing_id_result("KYC", "sender.account_id")
        )

        # Device registry — sender device
        t_device = asyncio.ensure_future(
            make_task("DEVICE_REGISTRY", check_device, sender_account_id, device_id, as_of)
            if (sender_account_id and device_id) else _missing_id_result(
                "DEVICE_REGISTRY", "sender.account_id and device.device_id"
            )
        )

        # Beneficiary — receiver account
        t_beneficiary = asyncio.ensure_future(
            make_task("BENEFICIARY", get_beneficiary, receiver_account_id, as_of)
            if receiver_account_id else _missing_id_result("BENEFICIARY", "receiver.account_id")
        )

        # Sanctions — by customer name (subject screening). When the
        # transaction carries no sender name, screen the KYC customer name.
        async def _subject_screen():
            name = customer_name
            if not name:
                kyc_res, _ = await t_kyc
                kyc_data = getattr(kyc_res, "data", None) if kyc_res is not None else None
                if kyc_data is not None and kyc_data.customer_name:
                    name = kyc_data.customer_name
                    name_notes.append(
                        "Sanctions subject screening used the KYC customer name "
                        "(transaction carried no sender name)."
                    )
            if not name:
                return await _missing_id_result(
                    "SANCTIONS_SUBJECT", "sender.account_name or KYC customer_name"
                )
            return await make_task("SANCTIONS_SUBJECT", screen_subject, name)

        t_sanctions_subject = asyncio.ensure_future(_subject_screen())

        # Sanctions — by account ID
        t_sanctions_account = asyncio.ensure_future(
            make_task("SANCTIONS_ACCOUNT", screen_account, sender_account_id)
            if sender_account_id else _missing_id_result("SANCTIONS_ACCOUNT", "sender.account_id")
        )

        # Geolocation
        t_geolocation = asyncio.ensure_future(
            make_task(
                "GEOLOCATION",
                check_geolocation,
                sender_account_id, tx_lat, tx_lon, tx_city, tx_country,
            )
            if sender_account_id else _missing_id_result("GEOLOCATION", "sender.account_id")
        )

        # News — always attempted with the best available query
        def _news_search():
            return news_provider.search(query=news_query)

        t_news = asyncio.ensure_future(
            make_task("NEWS", _news_search)
        )

        # Wait for all tasks concurrently
        all_results = await asyncio.gather(
            t_banking, t_kyc, t_device, t_beneficiary,
            t_sanctions_subject, t_sanctions_account,
            t_geolocation, t_news,
        )

        (banking_result, banking_pr), \
        (kyc_result, kyc_pr), \
        (device_result, device_pr), \
        (beneficiary_result, beneficiary_pr), \
        (sanctions_subj_result, sanctions_subj_pr), \
        (sanctions_acc_result, sanctions_acc_pr), \
        (geo_result, geo_pr), \
        (news_result, news_pr) = all_results

        all_provider_results = [
            banking_pr, kyc_pr, device_pr, beneficiary_pr,
            sanctions_subj_pr, sanctions_acc_pr, geo_pr, news_pr,
        ]

        failed = [pr.provider_name for pr in all_provider_results if not pr.succeeded]
        succeeded = [pr.provider_name for pr in all_provider_results if pr.succeeded]

        warnings: list[str] = list(name_notes)
        if not sender_account_id:
            warnings.append(
                "sender.account_id is missing; Core Banking, KYC, "
                "Device Registry, Sanctions, and Geolocation could not be queried."
            )
        if not receiver_account_id:
            warnings.append("receiver.account_id is missing; Beneficiary could not be queried.")
        if not device_id:
            warnings.append("device.device_id is missing; Device Registry could not be queried.")
        if failed:
            warnings.append(
                f"Evidence is INCOMPLETE. Failed providers: {', '.join(failed)}. "
                "Missing evidence must not be interpreted as a safe/clean finding."
            )

        if len(failed) == len(all_provider_results):
            overall_status = Agent2Status.FAILED
        elif failed:
            overall_status = Agent2Status.PARTIAL
        else:
            overall_status = Agent2Status.COMPLETE

        return Agent2Output(
            transaction_id=tx_id,
            source_dataset=source_dataset,
            status=overall_status,
            warnings=warnings,
            agent1_output=agent1_output,
            core_banking=banking_result,
            kyc=kyc_result,
            device=device_result,
            beneficiary=beneficiary_result,
            sanctions_subject=sanctions_subj_result,
            sanctions_account=sanctions_acc_result,
            geolocation=geo_result,
            news=news_result,
            provider_results=all_provider_results,
            failed_providers=failed,
            successful_providers=succeeded,
        )


# ---------------------------------------------------------------------------
# Synchronous wrapper (for non-async callers)
# ---------------------------------------------------------------------------

def gather_evidence(
    transaction: CanonicalTransaction,
    agent1_output: Agent1Output,
    news_provider: Optional[BaseNewsProvider] = None,
    provider_timeout_sec: float = _PROVIDER_TIMEOUT_SEC,
) -> Agent2Output:
    """Synchronous wrapper around EvidenceGathererAgent.gather().

    Creates a new event loop or uses the running one where possible.
    For production use, prefer the async interface directly.
    """
    agent = EvidenceGathererAgent(
        provider_timeout_sec=provider_timeout_sec,
        news_provider=news_provider,
    )
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an event loop (e.g. FastAPI / pytest-asyncio)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, agent.gather(transaction, agent1_output))
                return future.result()
        else:
            return loop.run_until_complete(agent.gather(transaction, agent1_output))
    except RuntimeError:
        return asyncio.run(agent.gather(transaction, agent1_output))


# ---------------------------------------------------------------------------
# Helper: produce a "missing ID" no-op result without calling a provider
# ---------------------------------------------------------------------------

async def _missing_id_result(
    provider_name: str,
    missing_field: str,
) -> tuple[None, ProviderResult]:
    """Return a VALIDATION_ERROR result when a required identifier is absent."""
    pr = ProviderResult(
        provider_name=provider_name,
        status=EvidenceStatus.VALIDATION_ERROR,
        retrieved_at=datetime.now(timezone.utc),
        error_summary=(
            f"Required identifier '{missing_field}' not present "
            f"in CanonicalTransaction; '{provider_name}' was not called."
        ),
        timed_out=False,
    )
    return None, pr
