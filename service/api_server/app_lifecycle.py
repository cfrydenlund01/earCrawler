from __future__ import annotations

"""Lifecycle and middleware wiring helpers for API app startup."""

import os
from typing import Callable

from fastapi import FastAPI

from earCrawler.observability.config import ObservabilityConfig
from earCrawler.utils.log_json import JsonLogger

from .auth import ApiKeyResolver
from .config import ApiSettings
from .fuseki import FusekiClient, HttpFusekiClient, StubFusekiClient
from .logging_integration import ObservabilityMiddleware
from .middleware import (
    BodyLimitMiddleware,
    ConcurrencyGate,
    ConcurrencyLimitMiddleware,
    RequestContextMiddleware,
)
from .rag_support import RetrieverWarmupOutcome

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


def resolve_fuseki_client(
    settings: ApiSettings, fuseki_client: FusekiClient | None
) -> FusekiClient:
    """Resolve Fuseki client from explicit dependency or runtime settings."""

    if fuseki_client is not None:
        return fuseki_client

    embedded = os.getenv("EARCRAWLER_API_EMBEDDED_FIXTURE") == "1"
    if settings.fuseki_url:
        return HttpFusekiClient(
            endpoint=settings.fuseki_url, timeout=settings.request_timeout_seconds
        )
    responses = _EMBEDDED_FIXTURE if embedded else {}
    return StubFusekiClient(responses=responses)


def configure_middleware(
    app: FastAPI,
    *,
    settings: ApiSettings,
    concurrency_gate: ConcurrencyGate,
    resolver: ApiKeyResolver,
    observability: ObservabilityConfig,
    json_logger: JsonLogger,
) -> None:
    """Attach request middleware in the established order."""

    app.add_middleware(
        ObservabilityMiddleware, logger=json_logger, config=observability
    )
    app.add_middleware(BodyLimitMiddleware, limit_bytes=settings.request_body_limit)
    app.add_middleware(ConcurrencyLimitMiddleware, gate=concurrency_gate)
    app.add_middleware(
        RequestContextMiddleware,
        resolver=resolver,
        timeout_seconds=settings.request_timeout_seconds,
    )


def register_retriever_warmup(
    app: FastAPI,
    *,
    warm_retriever: Callable[..., RetrieverWarmupOutcome | None],
) -> None:
    """Register startup warmup with injectable warmup implementation."""

    async def _warm_retriever_on_startup() -> None:
        outcome = warm_retriever(
            app.state.runtime_state.retriever_runtime.retriever,
            request_logger=app.state.request_logger,
        )
        if outcome is not None:
            app.state.runtime_state.retriever_runtime.record_warmup(outcome)
            app.state.runtime_contract["runtime_state"] = (
                app.state.runtime_state.contract_payload()
            )
            app.state.runtime_contract["process_local_state"] = (
                app.state.runtime_state.process_local_state()
            )

    app.add_event_handler("startup", _warm_retriever_on_startup)


def register_shutdown_close_hook(
    app: FastAPI, *, fuseki_client: FusekiClient
) -> None:
    """Register async close hook for clients that expose ``aclose``."""

    close_hook = getattr(fuseki_client, "aclose", None)
    if callable(close_hook):
        app.add_event_handler("shutdown", close_hook)
