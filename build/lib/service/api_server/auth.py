from __future__ import annotations

"""Authentication helpers for API key and anonymous access."""

from dataclasses import dataclass
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

    def resolve(self, candidate: str) -> Optional[Identity]:
        for label, value in self._env_keys.items():
            if value and value == candidate:
                return Identity(key=f"api:{label}", display_name=label, authenticated=True, api_key_label=label)
        try:
            stored = keyring.get_password(self._service_name, candidate)
            if stored:
                return Identity(key=f"api:{candidate}", display_name=candidate, authenticated=True, api_key_label=candidate)
        except Exception:  # pragma: no cover - defensive for environments without keyring backend
            pass
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
