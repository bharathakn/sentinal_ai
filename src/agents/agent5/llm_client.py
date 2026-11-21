"""
Sentinel AI — Agent 5: LLM client.

A minimal client for Groq's OpenAI-compatible chat-completions endpoint,
using httpx (already a project dependency). Any failure raises
:class:`LLMUnavailable` with a sanitised reason; the API key never appears
in errors or logs.

Configuration (environment):
    GROQ_API_KEY          required for the LLM path
    GROQ_MODEL            default "openai/gpt-oss-120b"
    GROQ_TIMEOUT_SECONDS  default 45
    GROQ_MAX_COMPLETION_TOKENS  default 2500
    GROQ_MAX_RATE_LIMIT_WAIT    default 10 (seconds; one retry on HTTP 429
                                when Groq asks to wait at most this long)
    GROQ_TPM_LIMIT              default 8000; the completion allowance is
                                reduced so prompt + completion fit it
    GROQ_STRICT_SCHEMA          default true; for openai/gpt-oss models the
                                response is constrained to the JSON schema
                                (strict structured outputs). Other models use
                                JSON mode.

Free-tier Groq keys are limited to ~8,000 tokens per minute (prompt plus
max completion), so prompts are kept compact.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Protocol

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMUnavailable(Exception):
    """The LLM could not produce a response. Message is safe to log."""


class LLMGenerationError(LLMUnavailable):
    """The model produced output the provider rejected (e.g. invalid JSON).
    Unlike transport / auth / quota failures, asking again may succeed."""


class LLMClient(Protocol):
    provider: str
    model: str

    def complete_json(self, system: str, user: str, schema: Optional[dict] = None) -> str:
        """Return the raw JSON text produced by the model."""
        ...


class GroqClient:
    provider = "groq"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 timeout: Optional[float] = None, seed: int = 7) -> None:
        self._api_key = (api_key or os.environ.get("GROQ_API_KEY", "")).strip()
        if not self._api_key:
            raise LLMUnavailable("GROQ_API_KEY is not configured")
        self.model = model or os.environ.get("GROQ_MODEL", "").strip() or DEFAULT_GROQ_MODEL
        self._timeout = timeout or float(os.environ.get("GROQ_TIMEOUT_SECONDS", "45"))
        self._max_tokens = int(os.environ.get("GROQ_MAX_COMPLETION_TOKENS", "2500"))
        self._max_wait = float(os.environ.get("GROQ_MAX_RATE_LIMIT_WAIT", "10"))
        self._tpm_limit = int(os.environ.get("GROQ_TPM_LIMIT", "8000"))
        self._strict = os.environ.get("GROQ_STRICT_SCHEMA", "true").strip().lower() not in ("0", "false", "no")
        self._seed = seed

    def complete_json(self, system: str, user: str, schema: Optional[dict] = None) -> str:
        import httpx

        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "response_format": (
                {"type": "json_schema",
                 "json_schema": {"name": "report_sections", "strict": True, "schema": schema}}
                if schema is not None and self._strict and self.model.startswith("openai/gpt-oss")
                else {"type": "json_object"}),
            "temperature": 0.2,
            "seed": self._seed,
            "max_completion_tokens": self.completion_budget(system, user),
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
            body["include_reasoning"] = False
        r = self._post(httpx, body)
        if r.status_code == 429:
            wait = _retry_after_seconds(r)
            if wait is not None and wait <= self._max_wait:
                time.sleep(wait + 0.5)
                r = self._post(httpx, body)
        if r.status_code != 200:
            code = ""
            try:
                code = r.json().get("error", {}).get("code") or ""
            except Exception:  # noqa: BLE001
                pass
            msg = f"LLM HTTP {r.status_code}{(' ' + code) if code else ''}"
            if code == "json_validate_failed":
                raise LLMGenerationError(msg)
            raise LLMUnavailable(msg)
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001
            raise LLMUnavailable("LLM response missing content") from None
        if not content or not content.strip():
            raise LLMUnavailable("LLM returned empty content")
        return content

    def completion_budget(self, system: str, user: str) -> int:
        """Completion tokens that keep prompt + completion within the TPM limit.

        Prompt tokens are estimated conservatively at 3 characters per token.
        Never below 1200 (a report needs room); never above the configured max.
        """
        est_prompt = (len(system) + len(user)) // 3 + 200
        return max(1200, min(self._max_tokens, self._tpm_limit - est_prompt))

    def _post(self, httpx, body):  # noqa: ANN001
        try:
            return httpx.post(GROQ_URL, json=body, timeout=self._timeout,
                              headers={"Authorization": f"Bearer {self._api_key}"})
        except httpx.TimeoutException:
            raise LLMUnavailable("LLM request timed out") from None
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"LLM transport error: {type(exc).__name__}") from None


def _retry_after_seconds(r) -> Optional[float]:  # noqa: ANN001
    try:
        return float(r.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def client_from_env() -> Optional[LLMClient]:
    """Return a configured LLM client, or None when no LLM is configured.

    SENTINEL_REPORT_GENERATOR=template disables the LLM explicitly.
    """
    if os.environ.get("SENTINEL_REPORT_GENERATOR", "llm").strip().lower() == "template":
        return None
    provider = os.environ.get("LLM_PROVIDER", "groq").strip().lower() or "groq"
    if provider != "groq":
        return None  # only Groq is implemented; template writer is used
    try:
        return GroqClient()
    except LLMUnavailable:
        return None
