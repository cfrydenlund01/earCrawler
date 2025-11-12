from __future__ import annotations

"""In-memory rate limiting for the read-only API."""

from dataclasses import dataclass
import threading
import time
from typing import Dict, Tuple

from fastapi import Request

from .config import RateLimitConfig


@dataclass(slots=True)
class BucketState:
    tokens: float
    last_refill: float


class RateLimitExceeded(Exception):
    def __init__(
        self, retry_after: float, scope: str, limit: int, remaining: int
    ) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after = retry_after
        self.scope = scope
        self.limit = limit
        self.remaining = remaining


class RateLimiter:
    def __init__(self, config: RateLimitConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._buckets: Dict[Tuple[str, str], BucketState] = {}

    def _get_bucket(
        self, key: Tuple[str, str], refill_rate: float, capacity: int
    ) -> BucketState:
        now = time.monotonic()
        with self._lock:
            state = self._buckets.get(key)
            if state is None:
                state = BucketState(tokens=float(capacity), last_refill=now)
                self._buckets[key] = state
            else:
                elapsed = max(0.0, now - state.last_refill)
                state.tokens = min(capacity, state.tokens + elapsed * refill_rate)
                state.last_refill = now
            return state

    def _consume(
        self, key: Tuple[str, str], refill_rate: float, capacity: int
    ) -> Tuple[int, float]:
        state = self._get_bucket(key, refill_rate, capacity)
        if state.tokens >= 1:
            state.tokens -= 1
            remaining = max(0, int(state.tokens))
            return remaining, 0.0
        retry = (1 - state.tokens) / refill_rate if refill_rate else 60.0
        remaining = int(state.tokens)
        return remaining, retry

    def check(
        self, identity: str, scope: str, authenticated: bool
    ) -> Tuple[int, float, int]:
        if authenticated:
            limit_per_minute = self._config.authenticated_per_minute
            burst = self._config.authenticated_burst
        else:
            limit_per_minute = self._config.anonymous_per_minute
            burst = self._config.anonymous_burst
        refill_rate = limit_per_minute / 60.0
        capacity = max(limit_per_minute, burst)
        key = (scope, identity)
        remaining, retry_after = self._consume(key, refill_rate, capacity)
        return capacity, retry_after, remaining


async def enforce_rate_limits(request: Request, limiter: RateLimiter) -> None:
    identity = request.state.identity
    scope = request.state.rate_scope
    authenticated = getattr(identity, "authenticated", False)
    capacity, retry_after, remaining = limiter.check(
        identity.key, scope=scope, authenticated=authenticated
    )
    request.state.rate_limit = {
        "limit": capacity,
        "remaining": max(0, remaining),
        "retry_after": retry_after,
    }
    if retry_after > 0:
        raise RateLimitExceeded(
            retry_after=retry_after, scope=scope, limit=capacity, remaining=remaining
        )
