from __future__ import annotations

"""Authentication helpers for API key and anonymous access."""

from dataclasses import dataclass
import hmac
import os
from typing import Dict, Optional

import keyring
from fastapi import Request


@dataclass(slots=True)
class Identity:
    key: str
    display_name: str
    authenticated: bool
    api_key_label: Optional[str] = None


class ApiKeyResolver:
    def __init__(self, service_name: str = "EarCrawler-API") -> None:
        self._service_name = service_name
        self._env_keys = self._load_from_env()

    def _load_from_env(self) -> Dict[str, str]:
        data = os.getenv("EARCRAWLER_API_KEYS", "").strip()
        keys: Dict[str, str] = {}
        if not data:
            return keys
        for token in data.split(";"):
            if not token:
                continue
            if "=" not in token:
                continue
            label, value = token.split("=", 1)
            keys[label.strip()] = value.strip()
        return keys

    @staticmethod
    def _secrets_match(expected: str, provided: str) -> bool:
        return bool(expected and provided) and hmac.compare_digest(expected, provided)

    @staticmethod
    def _parse_labeled_key(candidate: str) -> Optional[tuple[str, str]]:
        if ":" not in candidate:
            return None
        label, secret = candidate.split(":", 1)
        label = label.strip()
        secret = secret.strip()
        if not label or not secret:
            return None
        return label, secret

    def _resolve_labeled(self, label: str, presented_secret: str) -> Optional[Identity]:
        env_secret = self._env_keys.get(label)
        if env_secret and self._secrets_match(env_secret, presented_secret):
            return Identity(
                key=f"api:{label}",
                display_name=label,
                authenticated=True,
                api_key_label=label,
            )
        try:
            stored = keyring.get_password(self._service_name, label)
        except (
            Exception
        ):  # pragma: no cover - defensive for environments without keyring backend
            return None
        if stored and self._secrets_match(stored, presented_secret):
            return Identity(
                key=f"api:{label}",
                display_name=label,
                authenticated=True,
                api_key_label=label,
            )
        return None

    def resolve(self, candidate: str) -> Optional[Identity]:
        parsed = self._parse_labeled_key(candidate)
        if parsed:
            label, presented_secret = parsed
            return self._resolve_labeled(label, presented_secret)
        for label, value in self._env_keys.items():
            if value and self._secrets_match(value, candidate):
                return Identity(
                    key=f"api:{label}",
                    display_name=label,
                    authenticated=True,
                    api_key_label=label,
                )
        return None


def resolve_identity(request: Request, resolver: ApiKeyResolver) -> Identity:
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        identity = resolver.resolve(api_key)
        if identity:
            return identity
    client = request.client
    host = client.host if client else "unknown"
    return Identity(key=f"ip:{host}", display_name=host, authenticated=False)
