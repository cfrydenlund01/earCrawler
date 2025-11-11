from __future__ import annotations

"""ASGI middleware hooking structured logging and security headers."""

import asyncio
import time
from typing import Any, Callable, Awaitable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from earCrawler.observability.config import ObservabilityConfig
from earCrawler.utils.log_json import JsonLogger


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        logger: JsonLogger,
        config: ObservabilityConfig,
    ) -> None:
        super().__init__(app)
        self._logger = logger
        self._config = config

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        error: Exception | None = None
        status_code: int | None = None
        continue_log = True
        entry: dict[str, Any] | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:  # pragma: no cover - bubbled to FastAPI handler
            error = exc
            status_code = getattr(exc, "status_code", 500)
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 3)
            if response is not None:
                _apply_security_headers(request, response)
            if not self._config.request_logging_enabled:
                continue_log = False
            else:
                continue_log = True
            level = "INFO"
            event = "request"
            details: dict[str, Any] = {
                "method": request.method,
                "client": request.client.host if request.client else None,
            }
            rate_limit = getattr(request.state, "rate_limit", None)
            if rate_limit:
                details["rate_limit"] = rate_limit
            identity = getattr(request.state, "identity", None)
            if identity is not None:
                details["subject"] = getattr(identity, "key", None)
            if error is not None or (status_code or 0) >= 500:
                level = "ERROR"
                event = "request_error"
                details["error"] = repr(error) if error is not None else "status >= 500"
            elif (status_code or 0) >= 400:
                level = "WARNING"
            trace_id = getattr(request.state, "trace_id", "")
            route = request.url.path
            if continue_log:
                entry = self._logger.emit(
                    level,
                    event,
                    trace_id=trace_id,
                    route=route,
                    latency_ms=duration_ms,
                    status=status_code,
                    details=details,
                )
            if entry:
                await self._forward_log(request, entry, level)
        return response

    async def _forward_log(self, request: Request, entry: dict[str, Any], level: str) -> None:
        queue = getattr(request.app.state, "request_log_queue", None)
        if queue is None:
            return
        try:
            queue.put_nowait(entry)
            return
        except asyncio.QueueFull:
            if level.upper() not in {"ERROR", "WARNING", "CRITICAL"}:
                return
        try:
            await asyncio.wait_for(queue.put(entry), timeout=0.02)
        except (asyncio.TimeoutError, asyncio.QueueFull):
            return


def _apply_security_headers(request: Request, response: Response) -> None:
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/docs"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'",
        )


__all__ = ["ObservabilityMiddleware"]
