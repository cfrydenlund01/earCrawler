"""Helpers for retrieving secrets from env vars or Windows Credential Manager."""
from __future__ import annotations

import os

try:  # pragma: no cover - optional dependency
    import keyring
except Exception:  # pragma: no cover - keyring missing
    keyring = None  # type: ignore


def get_secret(name: str, *, fallback: str | None = None) -> str:
    """Return a secret from environment or Windows Credential Manager.

    Parameters
    ----------
    name:
        Environment variable and credential name.
    fallback:
        Value to return when the secret is absent. If ``None`` and the secret
        cannot be found, :class:`RuntimeError` is raised.
    """

    env = os.getenv(name)
    if env:
        return env
    if keyring is not None:  # pragma: no cover - platform specific
        for service in ("earCrawler", "EAR_AI"):
            try:
                value = keyring.get_password(service, name)
                if value:
                    return value
            except Exception:
                continue
    if fallback is not None:
        return fallback
    raise RuntimeError(f"Secret {name} not found")
