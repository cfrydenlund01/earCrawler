"""Multi-provider LLM client (OpenRouter, NVIDIA NIM, Groq) with budget and secrets integration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import requests

from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.utils import budget
from earCrawler.utils.log_json import JsonLogger

_logger = JsonLogger("llm-client")


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider call cannot be completed."""


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

    try:
        with budget.consume(f"llm:{provider}", limit=request_limit):
            resp = session.post(url, headers=headers, json=payload, timeout=timeout)
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
        _logger.error(
            "llm.http_status",
            provider=provider,
            status=resp.status_code,
            body=detail,
        )
        raise LLMProviderError(
            f"{provider} responded with {resp.status_code}: {detail}"
        )

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

    result = _chat_request(
        session=session,
        provider=provider_cfg.provider,
        api_key=provider_cfg.api_key,
        model=provider_cfg.model,
        base_url=provider_cfg.base_url,
        messages=messages,
        timeout=resolved_timeout,
        request_limit=provider_cfg.request_limit,
    )
    return result.content


__all__ = ["generate_chat", "LLMProviderError"]
