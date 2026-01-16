from __future__ import annotations

"""Helpers for loading LLM provider settings from env/keyring and an optional secrets file."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from earCrawler.utils.secure_store import get_secret


_DEFAULTS = {
    "nvidia_nim": {
        "model": "mistral-7b-instruct-v0.2",
        "base_url": "",
    },
    "groq": {
        # Keep this in sync with GROQ_MODEL in config/llm_secrets.example.env.
        # Default to the larger Groq model for higher quality answers.
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
    },
}


@dataclass
class ProviderConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    request_limit: int | None = None


@dataclass
class LLMConfig:
    provider: ProviderConfig
    enable_remote: bool


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a simple KEY=VALUE env-style file."""

    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_llm_secrets(
    path: Path | None = None, *, override_existing: bool = False
) -> None:
    """Load optional secrets file.

    Parameters
    ----------
    path:
        Path to the secrets env-style file.
    override_existing:
        When True, values from the file overwrite existing environment variables.
        This is useful when a previous session left empty or stale values in the
        environment and we want to ensure the file contents are authoritative.
    """

    if os.getenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "0") == "1":
        return

    if path is None:
        override_path = os.getenv("EARCRAWLER_LLM_SECRETS_PATH")
        if override_path:
            path = Path(override_path)

    secrets_path = path or Path("config") / "llm_secrets.env"
    values = _parse_env_file(secrets_path)
    for key, value in values.items():
        if not key or not value:
            continue
        if override_existing or key not in os.environ:
            os.environ[key] = value


def _get_limit(provider: str) -> int | None:
    """Resolve a soft request budget for a provider."""

    provider_env = os.getenv(f"LLM_{provider.upper()}_MAX_CALLS")
    if provider_env:
        try:
            return int(provider_env)
        except ValueError:
            return None
    generic_env = os.getenv("LLM_MAX_CALLS")
    if generic_env:
        try:
            return int(generic_env)
        except ValueError:
            return None
    return None


def _resolve_provider_model(
    provider: str, model_override: str | None
) -> Tuple[str, str]:
    defaults = _DEFAULTS.get(provider, {})
    resolved_model = (
        model_override
        or os.getenv(f"{provider.upper()}_MODEL")
        or defaults.get("model")
        or ""
    )
    return provider, resolved_model


def get_llm_config(
    *, provider_override: str | None = None, model_override: str | None = None
) -> LLMConfig:
    """Resolve LLM provider configuration using env, keyring, and defaults."""

    load_llm_secrets(override_existing=False)

    provider = (
        (provider_override or os.getenv("LLM_PROVIDER") or "groq").strip().lower()
    )
    provider, model = _resolve_provider_model(provider, model_override)

    defaults = _DEFAULTS.get(provider, {})
    base_url = os.getenv(f"{provider.upper()}_BASE_URL") or defaults.get("base_url", "")

    # API keys respect env > keyring (via get_secret) and fall back to empty string.
    api_key = get_secret(f"{provider.upper()}_API_KEY", fallback="")

    request_limit = _get_limit(provider)

    enable_remote = os.getenv("EARCRAWLER_ENABLE_REMOTE_LLM", "0") == "1"

    provider_cfg = ProviderConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url or "",
        request_limit=request_limit,
    )
    return LLMConfig(provider=provider_cfg, enable_remote=enable_remote)


__all__ = ["LLMConfig", "ProviderConfig", "get_llm_config", "load_llm_secrets"]
