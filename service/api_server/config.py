from __future__ import annotations

"""Configuration helpers for the read-only API facade."""

from dataclasses import dataclass, field
import os
from typing import Optional

SUPPORTED_RUNTIME_TOPOLOGY = "single_host"


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
    enable_search: bool = False
    declared_instance_count: int = 1
    allow_unsupported_multi_instance: bool = False
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)

    @classmethod
    def from_env(cls) -> "ApiSettings":
        fuseki_url = os.getenv("EARCRAWLER_FUSEKI_URL")
        host = os.getenv("EARCRAWLER_API_HOST", "127.0.0.1")
        port = int(os.getenv("EARCRAWLER_API_PORT", "9001"))
        request_body_limit = int(os.getenv("EARCRAWLER_API_BODY_LIMIT", str(32 * 1024)))
        request_timeout_seconds = float(os.getenv("EARCRAWLER_API_TIMEOUT", "5"))
        concurrency_limit = int(os.getenv("EARCRAWLER_API_CONCURRENCY", "16"))
        enable_search = os.getenv("EARCRAWLER_API_ENABLE_SEARCH", "0") == "1"
        declared_instance_count = int(os.getenv("EARCRAWLER_API_INSTANCE_COUNT", "1"))
        allow_unsupported_multi_instance = (
            os.getenv("EARCRAWLER_ALLOW_UNSUPPORTED_MULTI_INSTANCE", "0") == "1"
        )
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
            enable_search=enable_search,
            declared_instance_count=declared_instance_count,
            allow_unsupported_multi_instance=allow_unsupported_multi_instance,
            rate_limits=rate_limits,
        )

    def validate_runtime_contract(self) -> None:
        if self.declared_instance_count < 1:
            raise ValueError("EARCRAWLER_API_INSTANCE_COUNT must be >= 1.")
        if (
            self.declared_instance_count != 1
            and not self.allow_unsupported_multi_instance
        ):
            raise ValueError(
                "EarCrawler supports one API service instance per host. "
                "Runtime state for rate limits, request concurrency, the RAG query cache, "
                "and retriever warm state is process-local. "
                "Set EARCRAWLER_ALLOW_UNSUPPORTED_MULTI_INSTANCE=1 only for local experiments."
            )
