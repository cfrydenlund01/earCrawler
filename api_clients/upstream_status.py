"""Shared upstream status taxonomy for API client operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, Literal, TypeVar


UpstreamState = Literal[
    "ok",
    "no_results",
    "missing_credentials",
    "upstream_unavailable",
    "invalid_response",
    "retry_exhausted",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class UpstreamStatus:
    """Status emitted by an upstream client operation."""

    source: str
    operation: str
    state: UpstreamState
    message: str | None = None
    status_code: int | None = None
    retry_attempts: int | None = None
    result_count: int | None = None
    cache_hit: bool | None = None
    cache_age_seconds: float | None = None
    timestamp: str = field(default_factory=_utc_now)

    @property
    def degraded(self) -> bool:
        return self.state not in {"ok", "no_results"}

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "source": self.source,
            "operation": self.operation,
            "state": self.state,
            "timestamp": self.timestamp,
        }
        if self.message:
            payload["message"] = self.message
        if self.status_code is not None:
            payload["status_code"] = int(self.status_code)
        if self.retry_attempts is not None:
            payload["retry_attempts"] = int(self.retry_attempts)
        if self.result_count is not None:
            payload["result_count"] = int(self.result_count)
        if self.cache_hit is not None:
            payload["cache_hit"] = bool(self.cache_hit)
        if self.cache_age_seconds is not None:
            payload["cache_age_seconds"] = round(float(self.cache_age_seconds), 3)
        return payload


T = TypeVar("T")


@dataclass(frozen=True)
class UpstreamResult(Generic[T]):
    """Typed operation result containing payload plus explicit upstream status."""

    data: T
    status: UpstreamStatus

    @property
    def state(self) -> UpstreamState:
        return self.status.state

    @property
    def degraded(self) -> bool:
        return self.status.degraded

    def as_dict(self) -> dict[str, object]:
        payload = self.status.as_dict()
        payload["degraded"] = self.degraded
        return payload


class UpstreamStatusTracker:
    """Track the latest status for each operation in a single source client."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._latest: dict[str, UpstreamStatus] = {}

    def set(
        self,
        operation: str,
        state: UpstreamState,
        *,
        message: str | None = None,
        status_code: int | None = None,
        retry_attempts: int | None = None,
        result_count: int | None = None,
        cache_hit: bool | None = None,
        cache_age_seconds: float | None = None,
    ) -> UpstreamStatus:
        status = UpstreamStatus(
            source=self._source,
            operation=operation,
            state=state,
            message=message,
            status_code=status_code,
            retry_attempts=retry_attempts,
            result_count=result_count,
            cache_hit=cache_hit,
            cache_age_seconds=cache_age_seconds,
        )
        self._latest[operation] = status
        return status

    def get(self, operation: str | None = None) -> UpstreamStatus | None:
        if operation is None:
            if not self._latest:
                return None
            return max(self._latest.values(), key=lambda item: item.timestamp)
        return self._latest.get(operation)

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {name: self._latest[name].as_dict() for name in sorted(self._latest)}

__all__ = ["UpstreamState", "UpstreamStatus", "UpstreamResult", "UpstreamStatusTracker"]
