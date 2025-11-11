from __future__ import annotations

"""Structured JSON logger with B.13-aligned redaction."""

import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, MutableMapping

from earCrawler.utils.eventlog import write_event_log

EMAIL_RE = __import__("re").compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_RE = __import__("re").compile(r"(?:bearer\s+)?[A-Za-z0-9\-_=]{20,}", __import__("re").IGNORECASE)
PATH_RE = __import__("re").compile(r"(?:[A-Za-z]:\\\\[^\s]+|/[^\s]+)")
URL_QUERY_RE = __import__("re").compile(r"https?://[^\s?]+\?[^\s]+")
GUID_RE = __import__("re").compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _scrub(value: str) -> str:
    value = EMAIL_RE.sub("[redacted]", value)
    value = TOKEN_RE.sub("[redacted]", value)
    value = PATH_RE.sub("[path]", value)
    value = URL_QUERY_RE.sub(lambda m: m.group(0).split("?")[0], value)
    value = GUID_RE.sub("[guid]", value)
    return value


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (int, float, bool)):
        return obj
    if obj is None:
        return None
    return _scrub(str(obj))


def _truncate(details: Mapping[str, Any] | Iterable[Any], max_bytes: int) -> Any:
    if max_bytes <= 0:
        return details
    serialized = json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    blob = serialized.encode("utf-8")
    if len(blob) <= max_bytes:
        return details
    preview = blob[:max_bytes].decode("utf-8", errors="ignore")
    return {"note": "truncated", "preview": preview}


class JsonLogger:
    """Emit structured JSON events with consistent keys."""

    def __init__(
        self,
        service: str,
        *,
        logger: logging.Logger | None = None,
        eventlog_enabled: bool = False,
        max_details_bytes: int = 4096,
        sample_rate: float = 1.0,
    ) -> None:
        self._service = service
        self._logger = logger or logging.getLogger(f"earcrawler.{service}.json")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)
        self._eventlog_enabled = eventlog_enabled
        self._max_details_bytes = max(0, int(max_details_bytes))
        self._sample_rate = max(0.0, min(1.0, float(sample_rate)))

    def info(self, event: str, **fields: Any) -> None:
        return self._emit("INFO", event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        return self._emit("WARNING", event, fields)

    def error(self, event: str, **fields: Any) -> None:
        return self._emit("ERROR", event, fields)

    def emit(self, level: str, event: str, **fields: Any) -> None:
        return self._emit(level.upper(), event, dict(fields))

    def should_sample(self) -> bool:
        if self._sample_rate >= 1.0:
            return True
        return random.random() <= self._sample_rate

    def _emit(self, level: str, event: str, fields: MutableMapping[str, Any]) -> dict[str, Any] | None:
        if not self.should_sample():
            return None
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "service": self._service,
            "event": event,
        }
        for key in ("trace_id", "route", "latency_ms", "status"):
            value = fields.pop(key, None)
            if value is not None:
                entry[key] = value
        details = fields.pop("details", None)
        if details is not None:
            sanitized = _sanitize(details)
            entry["details"] = _truncate(sanitized, self._max_details_bytes)
        if fields:
            residual = _truncate(_sanitize(fields), self._max_details_bytes)
            if "details" in entry and isinstance(entry["details"], dict) and isinstance(residual, dict):
                entry["details"].update(residual)
            else:
                entry["details"] = residual
        payload = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._logger.log(_LEVEL_MAP.get(level.upper(), logging.INFO), payload)
        if self._eventlog_enabled and entry.get("level") in {"ERROR", "WARNING"}:
            summary = event
            detail = entry.get("details")
            if isinstance(detail, dict):
                reason = detail.get("reason") or detail.get("message") or detail.get("error")
                if reason:
                    summary = f"{event}: {reason}"
            write_event_log(summary[:300], level=entry["level"])
        return entry


__all__ = ["JsonLogger"]
