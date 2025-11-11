from __future__ import annotations

"""Loader for observability configuration shared across probes and services."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(slots=True)
class HealthBudgets:
    """Collection of health-check budgets with conservative defaults."""

    fuseki_ping_ms: int = 750
    fuseki_select_ms: int = 1500
    api_timeout_ms: int = 1000
    disk_min_free_mb: int = 512
    rate_limit_min_capacity: int = 10


@dataclass(slots=True)
class RequestHttpSinkConfig:
    """Settings for forwarding request logs to an HTTP endpoint."""

    enabled: bool = False
    endpoint: str | None = None
    batch_size: int = 50
    flush_ms: int = 1000
    queue_max: int = 1000


@dataclass(slots=True)
class ObservabilityConfig:
    """Runtime toggles for structured logging and health checks."""

    request_logging_enabled: bool = True
    request_logging_sample_rate: float = 1.0
    request_logging_max_details_bytes: int = 4096
    eventlog_enabled: bool = True
    health: HealthBudgets = field(default_factory=HealthBudgets)
    request_http_sink: RequestHttpSinkConfig = field(default_factory=RequestHttpSinkConfig)


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive guard
        return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover
        return default


def _load_health(data: Mapping[str, Any] | None) -> HealthBudgets:
    if not data:
        return HealthBudgets()
    return HealthBudgets(
        fuseki_ping_ms=_coerce_int(data.get("fuseki_ping_ms"), 750),
        fuseki_select_ms=_coerce_int(data.get("fuseki_select_ms"), 1500),
        api_timeout_ms=_coerce_int(data.get("api_timeout_ms"), 1000),
        disk_min_free_mb=_coerce_int(data.get("disk_min_free_mb"), 512),
        rate_limit_min_capacity=_coerce_int(data.get("rate_limit_min_capacity"), 10),
    )


def _load_http_sink(data: Mapping[str, Any] | None) -> RequestHttpSinkConfig:
    if not data:
        return RequestHttpSinkConfig()
    return RequestHttpSinkConfig(
        enabled=bool(data.get("enabled", False)),
        endpoint=data.get("endpoint"),
        batch_size=max(1, _coerce_int(data.get("batch_size"), 50)),
        flush_ms=max(100, _coerce_int(data.get("flush_ms"), 1000)),
        queue_max=max(10, _coerce_int(data.get("queue_max"), 1000)),
    )


def load_observability_config(path: Path | None = None) -> ObservabilityConfig:
    """Load observability settings from YAML with safe defaults."""

    if path is None:
        path = Path(__file__).resolve().parents[1] / "service" / "config" / "observability.yml"
    if not path.exists():
        return ObservabilityConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    health = _load_health(raw.get("health"))
    sample_rate = max(0.0, min(1.0, _coerce_float(raw.get("request_logging", {}).get("sample_rate"), 1.0)))
    max_details = _coerce_int(raw.get("request_logging", {}).get("max_details_bytes"), 4096)
    enabled = bool(raw.get("request_logging", {}).get("enabled", True))
    eventlog_enabled = bool(raw.get("eventlog", {}).get("enabled", True))
    http_sink = _load_http_sink(raw.get("request_http_sink"))
    return ObservabilityConfig(
        request_logging_enabled=enabled,
        request_logging_sample_rate=sample_rate,
        request_logging_max_details_bytes=max(0, max_details),
        eventlog_enabled=eventlog_enabled,
        health=health,
        request_http_sink=http_sink,
    )


__all__ = [
    "HealthBudgets",
    "RequestHttpSinkConfig",
    "ObservabilityConfig",
    "load_observability_config",
]
