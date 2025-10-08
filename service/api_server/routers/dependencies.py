from __future__ import annotations

from fastapi import Depends, Request

from ..fuseki import FusekiGateway
from ..limits import RateLimiter, enforce_rate_limits


def get_gateway(request: Request) -> FusekiGateway:
    return request.app.state.gateway


def get_registry(request: Request):  # pragma: no cover - convenience
    return request.app.state.registry


def rate_limit(scope: str):
    async def dependency(request: Request, limiter: RateLimiter = Depends(get_limiter)) -> None:
        request.state.rate_scope = scope
        await enforce_rate_limits(request, limiter)

    return dependency


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter
