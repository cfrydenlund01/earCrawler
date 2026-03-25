from __future__ import annotations

"""Application factory for the read-only API facade."""

from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from earCrawler import __version__ as package_version
from earCrawler.observability import load_observability_config
from earCrawler.utils.log_json import JsonLogger

from .app_contract import build_runtime_contract
from .app_lifecycle import (
    configure_middleware,
    register_retriever_warmup,
    register_shutdown_close_hook,
    resolve_fuseki_client,
)
from .app_request_logs import configure_request_log_sink
from .app_routes import register_docs_routes, register_exception_handlers
from .auth import ApiKeyResolver
from .capability_registry import load_capability_registry
from .config import ApiSettings
from .fuseki import FusekiClient, FusekiGateway
from .rag_support import (
    RagQueryCache,
    RetrieverProtocol,
    load_retriever,
    warm_retriever_if_enabled,
)
from .routers import build_router
from .runtime_state import ApiRuntimeState, build_process_local_runtime_state
from .templates import TemplateRegistry


def create_app(
    settings: Optional[ApiSettings] = None,
    *,
    registry: Optional[TemplateRegistry] = None,
    fuseki_client: Optional[FusekiClient] = None,
    retriever: Optional[RetrieverProtocol] = None,
    rag_cache: Optional[RagQueryCache] = None,
    runtime_state: Optional[ApiRuntimeState] = None,
) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    settings.validate_runtime_contract()
    registry = registry or TemplateRegistry.load_default()
    resolver = ApiKeyResolver()
    fuseki_client = resolve_fuseki_client(settings, fuseki_client)
    gateway = FusekiGateway(registry=registry, client=fuseki_client)
    if (
        runtime_state is not None
        and rag_cache is not None
        and runtime_state.rag_query_cache is not rag_cache
    ):
        raise ValueError(
            "create_app received both runtime_state and a different rag_cache."
        )
    if runtime_state is not None:
        if (
            retriever is not None
            and runtime_state.retriever_runtime.retriever is not retriever
        ):
            raise ValueError(
                "create_app received both runtime_state and a different retriever."
            )
    else:
        retriever = retriever or load_retriever()
        runtime_state = build_process_local_runtime_state(
            settings,
            rag_query_cache=rag_cache,
            retriever=retriever,
        )
    retriever = runtime_state.retriever_runtime.retriever

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

    capability_registry = load_capability_registry()
    runtime_contract = build_runtime_contract(
        settings,
        capability_registry=capability_registry,
        runtime_state=runtime_state,
    )
    if runtime_contract["override_active"]:
        json_logger.warning(
            "runtime.contract.override_enabled",
            declared_instance_count=settings.declared_instance_count,
            supported_topology="single_host",
        )

    configure_request_log_sink(
        app, observability=observability, json_logger=json_logger
    )
    configure_middleware(
        app,
        settings=settings,
        concurrency_gate=runtime_state.concurrency_gate,
        resolver=resolver,
        observability=observability,
        json_logger=json_logger,
    )

    app.state.registry = registry
    app.state.capability_registry = capability_registry
    app.state.gateway = gateway
    app.state.runtime_state = runtime_state
    app.state.rate_limiter = runtime_state.rate_limiter
    app.state.observability = observability
    app.state.request_logger = json_logger
    app.state.runtime_contract = runtime_contract
    app.state.rag_cache = runtime_state.rag_query_cache
    app.state.rag_retriever = retriever

    register_retriever_warmup(app, warm_retriever=warm_retriever_if_enabled)

    router = build_router(enable_search=settings.enable_search)
    app.include_router(router)

    register_shutdown_close_hook(app, fuseki_client=fuseki_client)
    register_docs_routes(app)
    register_exception_handlers(app)

    return app


app = create_app()
