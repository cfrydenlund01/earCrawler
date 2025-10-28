from __future__ import annotations

import os
import re
from typing import Any, Dict

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_RE = re.compile(r"(?:bearer\s+)?[A-Za-z0-9\-_=]{20,}", re.IGNORECASE)
PATH_RE = re.compile(r"(?:[A-Za-z]:\\\\[^\s]+|/[^\s]+)")
URL_QUERY_RE = re.compile(r"https?://[^\s?]+\?[^\s]+")
GUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

ALLOWED_KEYS = {
    "command",
    "duration_ms",
    "exit_code",
    "version",
    "os",
    "python",
    "device_id",
    "event",
    "ts",
    "error",
}


def _scrub_string(value: str) -> str:
    value = EMAIL_RE.sub("[redacted]", value)
    value = TOKEN_RE.sub("[redacted]", value)
    value = PATH_RE.sub("[path]", value)
    value = URL_QUERY_RE.sub(lambda m: m.group(0).split("?")[0], value)
    value = GUID_RE.sub("[guid]", value)
    return value


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items() if k in ALLOWED_KEYS}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        env_keys = [k for k in os.environ if k.endswith("_KEY") or k.endswith("_TOKEN") or k.endswith("_SECRET")]
        for k in env_keys:
            if os.getenv(k) and os.getenv(k) in obj:
                obj = obj.replace(os.getenv(k), "[redacted]")
        return _scrub_string(obj)
    return obj
