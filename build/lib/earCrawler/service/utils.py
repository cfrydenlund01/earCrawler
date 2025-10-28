from __future__ import annotations

import os

try:  # pragma: no cover - optional on non-Windows
    import win32cred  # type: ignore
except Exception:  # pragma: no cover - fallback when unavailable
    win32cred = None  # type: ignore


def get_secret(name: str) -> str | None:
    """Return secret ``name`` from env or Windows Credential Store."""
    val = os.getenv(name)
    if val:
        return val
    if win32cred is not None:  # pragma: no cover - platform specific
        try:
            cred = win32cred.CredRead(name, win32cred.CRED_TYPE_GENERIC, 0)
            return cred["CredentialBlob"].decode("utf-16")
        except Exception:
            return None
    return None
