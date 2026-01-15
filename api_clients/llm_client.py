"""Multi-provider LLM client (OpenRouter, NVIDIA NIM, Groq) with budget and secrets integration."""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import requests

from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.utils import budget
from earCrawler.utils.log_json import JsonLogger

_logger = JsonLogger("llm-client")


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider call cannot be completed."""


_RETRYABLE_STATUS_CODES_DEFAULT = {429}
_RETRY_AFTER_RE = re.compile(
    r"try again in\\s+(?P<seconds>\\d+(?:\\.\\d+)?)s", re.IGNORECASE
)
_LAST_REQUEST_AT = 0.0


@dataclass
class ChatResult:
    content: str
    raw: Dict[str, Any]


def _build_headers(provider: str, api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _choose_base_url(provider: str, configured: str) -> str:
    if configured:
        return configured.rstrip("/")
    if provider == "groq":
        return "https://api.groq.com/openai/v1"
    return ""


def _parse_retry_after_seconds(resp: requests.Response, detail: str) -> float | None:
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            return None

    match = _RETRY_AFTER_RE.search(detail or "")
    if match:
        try:
            return float(match.group("seconds"))
        except ValueError:
            return None
    return None


def _is_retryable_429(detail: str) -> bool:
    """Return True when a 429 is likely transient (e.g., TPM), False for hard quotas (e.g., TPD)."""

    detail_lower = (detail or "").lower()
    if "tokens per day" in detail_lower or "tpd" in detail_lower:
        return False
    return True


def _chat_request(
    session: requests.Session,
    provider: str,
    api_key: str,
    model: str,
    base_url: str,
    messages: List[Dict[str, str]],
    *,
    timeout: float,
    request_limit: int | None,
    retry_max_attempts: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
    retry_jitter_seconds: float,
) -> ChatResult:
    if not api_key:
        raise LLMProviderError(
            f"{provider} provider selected but {provider.upper()}_API_KEY is not configured. "
            "Set it via the secrets file, environment, or Windows Credential Store."
        )

    base = _choose_base_url(provider, base_url)
    if not base:
        raise LLMProviderError(
            f"{provider} base URL is not configured. Set {provider.upper()}_BASE_URL."
        )

    url = f"{base}/chat/completions"
    headers = _build_headers(provider, api_key)
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }

    _logger.info(
        "llm.request",
        provider=provider,
        model=model,
        url=url,
        limit=request_limit,
    )

    max_attempts = max(1, int(retry_max_attempts))
    min_interval_seconds = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "0.0"))
    max_wait_seconds = float(retry_max_seconds)
    for attempt in range(1, max_attempts + 1):
        try:
            with budget.consume(f"llm:{provider}", limit=request_limit):
                if min_interval_seconds > 0:
                    global _LAST_REQUEST_AT
                    now = time.monotonic()
                    sleep_for = min_interval_seconds - (now - _LAST_REQUEST_AT)
                    if sleep_for > 0:
                        _logger.info(
                            "llm.throttle",
                            provider=provider,
                            sleep_seconds=sleep_for,
                        )
                        time.sleep(sleep_for)
                    _LAST_REQUEST_AT = time.monotonic()
                resp = session.post(
                    url, headers=headers, json=payload, timeout=timeout
                )
        except budget.BudgetExceededError as exc:
            raise LLMProviderError(str(exc)) from exc
        except requests.RequestException as exc:
            _logger.error("llm.http_error", provider=provider, error=str(exc))
            raise LLMProviderError(f"HTTP error calling {provider}: {exc}") from exc

        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = json.dumps(resp.json())
            except Exception:
                pass

            retryable = resp.status_code in _RETRYABLE_STATUS_CODES_DEFAULT
            if retryable and resp.status_code == 429 and not _is_retryable_429(detail):
                retryable = False
            if retryable and attempt < max_attempts:
                retry_after = _parse_retry_after_seconds(resp, detail)
                backoff = retry_after
                if backoff is None:
                    backoff = min(
                        float(retry_max_seconds),
                        float(retry_base_seconds) * (2 ** (attempt - 1)),
                    )
                backoff = min(float(max_wait_seconds), float(backoff))
                backoff += random.uniform(0.0, float(retry_jitter_seconds))
                backoff = min(float(max_wait_seconds), float(backoff))

                _logger.warning(
                    "llm.retry",
                    provider=provider,
                    status=resp.status_code,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    sleep_seconds=backoff,
                )
                time.sleep(backoff)
                continue

            _logger.error(
                "llm.http_status",
                provider=provider,
                status=resp.status_code,
                body=detail,
            )
            raise LLMProviderError(
                f"{provider} responded with {resp.status_code}: {detail}"
            )

        break

    try:
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except Exception as exc:
        raise LLMProviderError(f"Failed to parse {provider} response: {exc}") from exc

    if not content:
        raise LLMProviderError(f"{provider} returned an empty response")

    return ChatResult(content=content, raw=data)


def generate_chat(
    messages: List[Dict[str, str]],
    provider: str | None = None,
    model: str | None = None,
    *,
    timeout: float | None = None,
) -> str:
    """Generate a chat completion using the selected provider."""

    config = get_llm_config(provider_override=provider, model_override=model)
    provider_cfg = config.provider

    if not config.enable_remote:
        raise LLMProviderError(
            "Remote LLM calls are disabled. Set EARCRAWLER_ENABLE_REMOTE_LLM=1 "
            "to enable networked providers."
        )

    session = requests.Session()
    session.trust_env = False
    resolved_timeout = timeout if timeout is not None else float(
        os.getenv("LLM_TIMEOUT_SECONDS", "30")
    )

    retry_max_attempts = int(os.getenv("LLM_RETRY_MAX_ATTEMPTS", "5"))
    retry_base_seconds = float(os.getenv("LLM_RETRY_BASE_SECONDS", "1.0"))
    retry_max_seconds = float(os.getenv("LLM_RETRY_MAX_SECONDS", "30.0"))
    retry_jitter_seconds = float(os.getenv("LLM_RETRY_JITTER_SECONDS", "0.25"))

    result = _chat_request(
        session=session,
        provider=provider_cfg.provider,
        api_key=provider_cfg.api_key,
        model=provider_cfg.model,
        base_url=provider_cfg.base_url,
        messages=messages,
        timeout=resolved_timeout,
        request_limit=provider_cfg.request_limit,
        retry_max_attempts=retry_max_attempts,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
        retry_jitter_seconds=retry_jitter_seconds,
    )
    return result.content


__all__ = ["generate_chat", "LLMProviderError"]
