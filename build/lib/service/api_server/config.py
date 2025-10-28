from __future__ import annotations

"""Configuration helpers for the read-only API facade."""

from dataclasses import dataclass, field
import os
from typing import Optional


@dataclass(slots=True)
class RateLimitConfig:
    """Container for rate limit policies."""

    anonymous_per_minute: int = 30
    authenticated_per_minute: int = 120
    anonymous_burst: int = 10
    authenticated_burst: int = 20


@dataclass(slots=True)
class ApiSettings:
    """Settings loaded from environment variables with sane defaults."""

    fuseki_url: Optional[str]
    host: str = "127.0.0.1"
    port: int = 9001
    request_body_limit: int = 32 * 1024
    request_timeout_seconds: float = 5.0
    concurrency_limit: int = 16
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)

    @classmethod
    def from_env(cls) -> "ApiSettings":
        fuseki_url = os.getenv("EARCRAWLER_FUSEKI_URL")
        host = os.getenv("EARCRAWLER_API_HOST", "127.0.0.1")
        port = int(os.getenv("EARCRAWLER_API_PORT", "9001"))
        request_body_limit = int(os.getenv("EARCRAWLER_API_BODY_LIMIT", str(32 * 1024)))
        request_timeout_seconds = float(os.getenv("EARCRAWLER_API_TIMEOUT", "5"))
        concurrency_limit = int(os.getenv("EARCRAWLER_API_CONCURRENCY", "16"))
        anonymous_limit = int(os.getenv("EARCRAWLER_API_ANON_PER_MIN", "30"))
        auth_limit = int(os.getenv("EARCRAWLER_API_AUTH_PER_MIN", "120"))
        anonymous_burst = int(os.getenv("EARCRAWLER_API_ANON_BURST", "10"))
        authenticated_burst = int(os.getenv("EARCRAWLER_API_AUTH_BURST", "20"))
        rate_limits = RateLimitConfig(
            anonymous_per_minute=anonymous_limit,
            authenticated_per_minute=auth_limit,
            anonymous_burst=anonymous_burst,
            authenticated_burst=authenticated_burst,
        )
        return cls(
            fuseki_url=fuseki_url,
            host=host,
            port=port,
            request_body_limit=request_body_limit,
            request_timeout_seconds=request_timeout_seconds,
            concurrency_limit=concurrency_limit,
            rate_limits=rate_limits,
        )
