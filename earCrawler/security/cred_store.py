from __future__ import annotations

import keyring
from typing import List

SERVICE = "EarCrawler"


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def get_secret(name: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except Exception:
        pass


def list_secrets() -> List[str]:
    try:
        kr = keyring.get_keyring()
        if hasattr(kr, "_storage"):
            return list(getattr(kr, "_storage").get(SERVICE, {}).keys())
    except Exception:
        return []
    return []
