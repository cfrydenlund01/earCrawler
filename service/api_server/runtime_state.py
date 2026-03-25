from __future__ import annotations

"""Explicit ownership for API runtime state that remains process-local."""

from dataclasses import dataclass

from .config import ApiSettings
from .limits import RATE_LIMITER_STORAGE_SCOPE, RateLimiter
from .middleware import ConcurrencyGate, REQUEST_CONCURRENCY_STORAGE_SCOPE
from .rag_support import (
    RAG_QUERY_CACHE_STORAGE_SCOPE,
    RETRIEVER_CACHE_STORAGE_SCOPE,
    RETRIEVER_WARM_STATE_STORAGE_SCOPE,
    NullRetriever,
    RagQueryCache,
    RetrieverProtocol,
    RetrieverWarmupOutcome,
    retriever_warmup_enabled,
    retriever_warmup_timeout_seconds,
)

PROCESS_LOCAL_RUNTIME_STATE_BACKEND = "process_local"


@dataclass(frozen=True, slots=True)
class RuntimeStateComponent:
    storage_scope: str
    owner: str


@dataclass(slots=True)
class RetrieverRuntimeState:
    """Runtime-owned retriever state that is intentionally process-local."""

    retriever: RetrieverProtocol
    startup_warmup_requested: bool
    startup_warmup_timeout_seconds: float
    startup_warmup_status: str
    startup_warmup_reason: str | None = None

    @classmethod
    def from_retriever(
        cls, retriever: RetrieverProtocol | None = None
    ) -> "RetrieverRuntimeState":
        requested = retriever_warmup_enabled()
        return cls(
            retriever=(
                retriever
                if retriever is not None
                else NullRetriever(reason="No retriever injected")
            ),
            startup_warmup_requested=requested,
            startup_warmup_timeout_seconds=retriever_warmup_timeout_seconds(),
            startup_warmup_status="pending" if requested else "not_requested",
        )

    def record_warmup(self, outcome: RetrieverWarmupOutcome) -> None:
        self.startup_warmup_requested = outcome.requested
        self.startup_warmup_timeout_seconds = outcome.timeout_seconds
        self.startup_warmup_status = outcome.status
        self.startup_warmup_reason = outcome.reason

    def contract_payload(self) -> dict[str, object]:
        return {
            "cache_storage_scope": RETRIEVER_CACHE_STORAGE_SCOPE,
            "warm_state_storage_scope": RETRIEVER_WARM_STATE_STORAGE_SCOPE,
            "enabled": bool(getattr(self.retriever, "enabled", True)),
            "ready": bool(getattr(self.retriever, "ready", True)),
            "startup_warmup": {
                "requested": self.startup_warmup_requested,
                "status": self.startup_warmup_status,
                "timeout_seconds": self.startup_warmup_timeout_seconds,
                "reason": self.startup_warmup_reason,
            },
        }


@dataclass(slots=True)
class ApiRuntimeState:
    """Container for runtime-owned state in the supported single-host topology."""

    rate_limiter: RateLimiter
    concurrency_gate: ConcurrencyGate
    rag_query_cache: RagQueryCache
    retriever_runtime: RetrieverRuntimeState
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
            "retriever_runtime": self.retriever_runtime.contract_payload(),
        }

    def components(self) -> dict[str, RuntimeStateComponent]:
        return {
            "rate_limits": RuntimeStateComponent(
                storage_scope=RATE_LIMITER_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "request_concurrency": RuntimeStateComponent(
                storage_scope=REQUEST_CONCURRENCY_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "rag_query_cache": RuntimeStateComponent(
                storage_scope=RAG_QUERY_CACHE_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "retriever_cache": RuntimeStateComponent(
                storage_scope=RETRIEVER_CACHE_STORAGE_SCOPE,
                owner="retriever_runtime",
            ),
            "retriever_warm_state": RuntimeStateComponent(
                storage_scope=RETRIEVER_WARM_STATE_STORAGE_SCOPE,
                owner="retriever_runtime",
            ),
        }


def build_process_local_runtime_state(
    settings: ApiSettings,
    *,
    rag_query_cache: RagQueryCache | None = None,
    retriever: RetrieverProtocol | None = None,
) -> ApiRuntimeState:
    return ApiRuntimeState(
        rate_limiter=RateLimiter(settings.rate_limits),
        concurrency_gate=ConcurrencyGate(settings.concurrency_limit),
        rag_query_cache=rag_query_cache or RagQueryCache(),
        retriever_runtime=RetrieverRuntimeState.from_retriever(retriever),
    )


__all__ = [
    "ApiRuntimeState",
    "PROCESS_LOCAL_RUNTIME_STATE_BACKEND",
    "RetrieverRuntimeState",
    "RuntimeStateComponent",
    "build_process_local_runtime_state",
]
