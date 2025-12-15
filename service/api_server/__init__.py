from __future__ import annotations

"""Application factory for the read-only API facade."""

import asyncio
import html
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from earCrawler import __version__ as package_version
from earCrawler.observability import load_observability_config
from earCrawler.telemetry.config import TelemetryConfig
from earCrawler.telemetry.sink_http import AsyncHTTPSink
from earCrawler.utils.log_json import JsonLogger

from .auth import ApiKeyResolver
from .config import ApiSettings
from .fuseki import FusekiClient, FusekiGateway, HttpFusekiClient, StubFusekiClient
from .limits import RateLimiter
from .logging_integration import ObservabilityMiddleware
from .middleware import (
    BodyLimitMiddleware,
    ConcurrencyLimitMiddleware,
    RequestContextMiddleware,
)
from .schemas import ProblemDetails
from .templates import TemplateRegistry
from .routers import build_router
from .rag_support import RagQueryCache, load_retriever, RetrieverProtocol

_DOCS_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.md"
_OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi" / "openapi.yaml"
_EMBEDDED_FIXTURE = {
    "entity_by_id": [
        {
            "entity": "urn:example:entity:1",
            "label": "Example Entity",
            "description": "Embedded fixture",
            "type": "http://schema.org/Thing",
            "sameAs": "http://example.com/entity",
            "attribute": "http://purl.org/dc/terms/identifier",
            "value": "FIX-001",
        }
    ],
    "search_entities": [
        {
            "entity": "urn:example:entity:1",
            "label": "Example Entity",
            "score": 0.9,
            "snippet": "Embedded search fixture",
        }
    ],
    "lineage_by_id": [
        {
            "source": "urn:example:entity:1",
            "relation": "http://www.w3.org/ns/prov#used",
            "target": "urn:example:artifact:2",
            "timestamp": "2023-01-02T00:00:00Z",
        }
    ],
}


def create_app(
    settings: Optional[ApiSettings] = None,
    *,
    registry: Optional[TemplateRegistry] = None,
    fuseki_client: Optional[FusekiClient] = None,
    retriever: Optional[RetrieverProtocol] = None,
    rag_cache: Optional[RagQueryCache] = None,
    mistral_service: Optional[object] = None,
) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    registry = registry or TemplateRegistry.load_default()
    resolver = ApiKeyResolver()
    if fuseki_client is None:
        embedded = os.getenv("EARCRAWLER_API_EMBEDDED_FIXTURE") == "1"
        if settings.fuseki_url:
            fuseki_client = HttpFusekiClient(
                endpoint=settings.fuseki_url, timeout=settings.request_timeout_seconds
            )
        else:
            responses = _EMBEDDED_FIXTURE if embedded else {}
            fuseki_client = StubFusekiClient(responses=responses)
    gateway = FusekiGateway(registry=registry, client=fuseki_client)
    rate_limiter = RateLimiter(settings.rate_limits)

    app = FastAPI(
        title="EarCrawler API",
        version=package_version,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        default_response_class=JSONResponse,
    )

    observability = load_observability_config()
    json_logger = JsonLogger(
        "api",
        eventlog_enabled=observability.eventlog_enabled,
        max_details_bytes=observability.request_logging_max_details_bytes,
        sample_rate=observability.request_logging_sample_rate,
    )

    app.state.request_log_queue = None
    app.state.request_log_task = None

    http_sink_cfg = observability.request_http_sink
    if http_sink_cfg.enabled and http_sink_cfg.endpoint:
        try:
            sink = AsyncHTTPSink(
                TelemetryConfig(enabled=True, endpoint=http_sink_cfg.endpoint)
            )
        except RuntimeError as exc:
            json_logger.warning("telemetry.http_sink.disabled", reason=str(exc))
        else:
            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(
                maxsize=http_sink_cfg.queue_max
            )
            flush_interval = max(0.1, http_sink_cfg.flush_ms / 1000.0)
            batch_size = max(1, http_sink_cfg.batch_size)

            async def _drain_request_logs() -> None:
                batch: list[dict[str, object]] = []
                try:
                    while True:
                        try:
                            item = await asyncio.wait_for(
                                queue.get(), timeout=flush_interval
                            )
                            batch.append(item)
                            if len(batch) >= batch_size:
                                await sink.send(list(batch))
                                batch.clear()
                        except asyncio.TimeoutError:
                            if batch:
                                await sink.send(list(batch))
                                batch.clear()
                except asyncio.CancelledError:
                    while True:
                        if batch:
                            await sink.send(list(batch))
                            batch.clear()
                        try:
                            batch.append(queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break
                    raise
                finally:
                    if batch:
                        await sink.send(list(batch))
                    await sink.aclose()

            async def _start_request_logs() -> None:
                app.state.request_log_task = asyncio.create_task(_drain_request_logs())

            async def _stop_request_logs() -> None:
                task = getattr(app.state, "request_log_task", None)
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    app.state.request_log_task = None
                else:
                    await sink.aclose()

            app.state.request_log_queue = queue
            app.add_event_handler("startup", _start_request_logs)
            app.add_event_handler("shutdown", _stop_request_logs)

    app.add_middleware(
        ObservabilityMiddleware, logger=json_logger, config=observability
    )
    app.add_middleware(BodyLimitMiddleware, limit_bytes=settings.request_body_limit)
    app.add_middleware(ConcurrencyLimitMiddleware, limit=settings.concurrency_limit)
    app.add_middleware(
        RequestContextMiddleware,
        resolver=resolver,
        timeout_seconds=settings.request_timeout_seconds,
    )

    app.state.registry = registry
    app.state.gateway = gateway
    app.state.rate_limiter = rate_limiter
    app.state.observability = observability
    app.state.request_logger = json_logger
    app.state.rag_cache = rag_cache or RagQueryCache()
    app.state.rag_retriever = retriever or load_retriever()
    if mistral_service is None:
        try:
            from .mistral_support import load_mistral_service
        except Exception:  # pragma: no cover - optional heavy import
            app.state.mistral_service = None
        else:
            app.state.mistral_service = load_mistral_service(app.state.rag_retriever)
    else:
        app.state.mistral_service = mistral_service

    router = build_router()
    app.include_router(router)

    # Ensure any pooled async HTTP clients are closed on shutdown.
    close_hook = getattr(fuseki_client, "aclose", None)
    if callable(close_hook):
        app.add_event_handler("shutdown", close_hook)

    @app.get("/docs", include_in_schema=False)
    async def docs() -> Response:
        body = _DOCS_PATH.read_text(encoding="utf-8")
        return Response(
            content=f"<html><body><pre>{html.escape(body)}</pre></body></html>",
            media_type="text/html",
        )

    @app.get("/openapi.yaml", include_in_schema=False)
    async def openapi_spec() -> Response:
        return Response(
            content=_OPENAPI_PATH.read_text(encoding="utf-8"),
            media_type="application/yaml",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "")
        detail = exc.errors()
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/validation",
            title="Validation Failed",
            status=422,
            detail=str(detail),
            instance=str(request.url),
            trace_id=trace_id,
        )
        return JSONResponse(
            status_code=422, content=problem.model_dump(exclude_none=True)
        )

    @app.exception_handler(HTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "")
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/http",
            title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            status=exc.status_code,
            detail=exc.detail if isinstance(exc.detail, str) else None,
            instance=str(request.url),
            trace_id=trace_id,
        )
        headers = {}
        if exc.headers:
            headers.update(exc.headers)
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(exclude_none=True),
            headers=headers,
        )

    return app


app = create_app()
