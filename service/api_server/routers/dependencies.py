from __future__ import annotations

from fastapi import Depends, Request

from ..fuseki import FusekiGateway
from ..limits import RateLimiter, enforce_rate_limits
from ..rag_support import RagQueryCache, RetrieverProtocol
from ..runtime_state import ApiRuntimeState


def get_gateway(request: Request) -> FusekiGateway:
    return request.app.state.gateway


def get_registry(request: Request):  # pragma: no cover - convenience
    return request.app.state.registry


def rate_limit(scope: str):
    async def dependency(
        request: Request, limiter: RateLimiter = Depends(get_limiter)
    ) -> None:
        request.state.rate_scope = scope
        await enforce_rate_limits(request, limiter)

    return dependency


def get_runtime_state(request: Request) -> ApiRuntimeState:
    return request.app.state.runtime_state


def get_limiter(request: Request) -> RateLimiter:
    return get_runtime_state(request).rate_limiter


def get_rag_cache(request: Request) -> RagQueryCache:
    return get_runtime_state(request).rag_query_cache


def get_retriever(request: Request) -> RetrieverProtocol:
    return get_runtime_state(request).retriever_runtime.retriever
