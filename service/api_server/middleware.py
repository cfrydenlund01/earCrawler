from __future__ import annotations

"""Custom ASGI middleware for the API facade."""

import asyncio
import json
import logging
import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .auth import ApiKeyResolver, Identity, resolve_identity
from .limits import RateLimitExceeded
from .schemas.errors import ProblemDetails

_logger = logging.getLogger("earcrawler.api.middleware")


class RequestContextMiddleware:
    def __init__(
        self, app: ASGIApp, resolver: ApiKeyResolver, timeout_seconds: float
    ) -> None:
        self.app = app
        self._resolver = resolver
        self._timeout = timeout_seconds

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        trace_id = uuid.uuid4().hex
        start = time.perf_counter()
        identity = resolve_identity(request, self._resolver)
        request.state.identity = identity
        request.state.trace_id = trace_id
        request.state.rate_limit = None
        request.state.rate_scope = request.url.path
        response_started = False

        async def send_with_headers(message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                duration = time.perf_counter() - start
                _inject_headers(
                    headers,
                    trace_id,
                    identity,
                    duration,
                    request.state.rate_limit,
                )
            await send(message)

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send_with_headers),
                timeout=self._timeout,
            )
        except RateLimitExceeded as exc:
            if response_started:
                raise
            response = _problem_response(
                status=429,
                problem=ProblemDetails(
                    type="https://earcrawler.gov/problems/rate-limit",
                    title="Too Many Requests",
                    status=429,
                    detail="Rate limit exceeded",
                    instance=str(request.url),
                    trace_id=trace_id,
                ),
                retry_after=exc.retry_after,
                rate_limit=request.state.rate_limit
                or {
                    "limit": exc.limit,
                    "remaining": max(0, exc.remaining),
                    "retry_after": exc.retry_after,
                },
                identity=identity,
                trace_id=trace_id,
            )
            await response(scope, receive, send)
        except asyncio.TimeoutError:
            if response_started:
                raise
            response = _problem_response(
                status=504,
                problem=ProblemDetails(
                    type="https://earcrawler.gov/problems/timeout",
                    title="Gateway Timeout",
                    status=504,
                    detail="The request exceeded the configured API timeout",
                    instance=str(request.url),
                    trace_id=trace_id,
                ),
                identity=identity,
                trace_id=trace_id,
            )
            await response(scope, receive, send)
        except Exception:
            if response_started:
                raise
            _logger.exception(
                "Unhandled API exception",
                extra={"trace_id": trace_id, "path": request.url.path},
            )
            response = _problem_response(
                status=500,
                problem=ProblemDetails(
                    type="https://earcrawler.gov/problems/internal",
                    title="Internal Server Error",
                    status=500,
                    detail="An unexpected server error occurred",
                    instance=str(request.url),
                    trace_id=trace_id,
                ),
                identity=identity,
                trace_id=trace_id,
            )
            await response(scope, receive, send)


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, limit: int) -> None:
        super().__init__(app)
        self._sem = asyncio.Semaphore(limit)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        async with self._sem:
            return await call_next(request)


class BodyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, limit_bytes: int) -> None:
        super().__init__(app)
        self._limit = limit_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        trace_id = getattr(request.state, "trace_id", "")
        identity = getattr(request.state, "identity", None)
        if length:
            try:
                declared_length = int(length)
            except ValueError:
                return _problem_response(
                    status=400,
                    problem=ProblemDetails(
                        type="https://earcrawler.gov/problems/invalid-content-length",
                        title="Bad Request",
                        status=400,
                        detail="Invalid Content-Length header",
                        instance=str(request.url),
                        trace_id=trace_id,
                    ),
                    identity=identity,
                    trace_id=trace_id,
                )
            if declared_length < 0:
                return _problem_response(
                    status=400,
                    problem=ProblemDetails(
                        type="https://earcrawler.gov/problems/invalid-content-length",
                        title="Bad Request",
                        status=400,
                        detail="Invalid Content-Length header",
                        instance=str(request.url),
                        trace_id=trace_id,
                    ),
                    identity=identity,
                    trace_id=trace_id,
                )
            if declared_length > self._limit:
                return _problem_response(
                    status=413,
                    problem=ProblemDetails(
                        type="https://earcrawler.gov/problems/payload-too-large",
                        title="Payload Too Large",
                        status=413,
                        detail=f"Request body exceeds {self._limit} bytes",
                        instance=str(request.url),
                        trace_id=trace_id,
                    ),
                    identity=identity,
                    trace_id=trace_id,
                )
        body = await request.body()
        if len(body) > self._limit:
            return _problem_response(
                status=413,
                problem=ProblemDetails(
                    type="https://earcrawler.gov/problems/payload-too-large",
                    title="Payload Too Large",
                    status=413,
                    detail=f"Request body exceeds {self._limit} bytes",
                    instance=str(request.url),
                    trace_id=trace_id,
                ),
                identity=identity,
                trace_id=trace_id,
            )
        request._body = body  # type: ignore[attr-defined]  # reuse body downstream
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/docs"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'",
            )
        return response


def _inject_headers(
    headers: Headers | dict,
    trace_id: str,
    identity: Identity,
    duration: float,
    rate_limit: dict | None,
) -> None:
    headers["X-Request-Id"] = trace_id
    headers["Server-Timing"] = f"app;dur={duration * 1000:.2f}"
    headers["X-Subject"] = identity.key
    if rate_limit:
        headers["X-RateLimit-Limit"] = str(rate_limit.get("limit", 0))
        headers["X-RateLimit-Remaining"] = str(max(0, rate_limit.get("remaining", 0)))
        if rate_limit.get("retry_after"):
            headers["Retry-After"] = str(int(rate_limit["retry_after"] + 0.5))


def _problem_response(
    *,
    status: int,
    problem: ProblemDetails,
    retry_after: float | None = None,
    rate_limit: dict | None = None,
    identity: Identity | None = None,
    trace_id: str | None = None,
) -> Response:
    payload = problem.model_dump(exclude_none=True)
    content = json.dumps(payload)
    headers = {
        "Content-Type": "application/problem+json",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    if identity is not None:
        headers["X-Subject"] = identity.key
    if trace_id:
        headers["X-Request-Id"] = trace_id
    if retry_after:
        headers["Retry-After"] = str(int(retry_after + 0.5))
    if rate_limit:
        headers["X-RateLimit-Limit"] = str(rate_limit.get("limit", 0))
        headers["X-RateLimit-Remaining"] = str(max(0, rate_limit.get("remaining", 0)))
    return Response(content=content, status_code=status, headers=headers)
