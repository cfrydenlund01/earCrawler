from __future__ import annotations

"""Explicit ownership for API runtime state that remains process-local."""

from dataclasses import dataclass

from .config import ApiSettings
from .limits import RATE_LIMITER_STORAGE_SCOPE, RateLimiter
from .rag_support import RAG_QUERY_CACHE_STORAGE_SCOPE, RagQueryCache

PROCESS_LOCAL_RUNTIME_STATE_BACKEND = "process_local"


@dataclass(frozen=True, slots=True)
class RuntimeStateComponent:
    storage_scope: str
    owner: str


@dataclass(slots=True)
class ApiRuntimeState:
    """Container for runtime-owned state in the supported single-host topology."""

    rate_limiter: RateLimiter
    rag_query_cache: RagQueryCache
    backend: str = PROCESS_LOCAL_RUNTIME_STATE_BACKEND

    def process_local_state(self) -> dict[str, str]:
        return {
            name: component.storage_scope
            for name, component in self.components().items()
        }

    def contract_payload(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "shared_state_ready": False,
            "components": {
                name: {
                    "storage_scope": component.storage_scope,
                    "owner": component.owner,
                }
                for name, component in self.components().items()
            },
        }

    def components(self) -> dict[str, RuntimeStateComponent]:
        return {
            "rate_limits": RuntimeStateComponent(
                storage_scope=RATE_LIMITER_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "rag_query_cache": RuntimeStateComponent(
                storage_scope=RAG_QUERY_CACHE_STORAGE_SCOPE,
                owner="runtime_state",
            ),
        }


def build_process_local_runtime_state(
    settings: ApiSettings,
    *,
    rag_query_cache: RagQueryCache | None = None,
) -> ApiRuntimeState:
    return ApiRuntimeState(
        rate_limiter=RateLimiter(settings.rate_limits),
        rag_query_cache=rag_query_cache or RagQueryCache(),
    )


__all__ = [
    "ApiRuntimeState",
    "PROCESS_LOCAL_RUNTIME_STATE_BACKEND",
    "RuntimeStateComponent",
    "build_process_local_runtime_state",
]
