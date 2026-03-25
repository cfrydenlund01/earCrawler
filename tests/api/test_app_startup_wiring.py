from __future__ import annotations

from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.rag_support import RetrieverWarmupOutcome


def test_startup_warmup_uses_app_retriever(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []

    def _spy(retriever, *, request_logger=None):
        calls.append((retriever, request_logger))
        return RetrieverWarmupOutcome(
            status="completed",
            requested=True,
            timeout_seconds=1.0,
            t_total_ms=0.5,
        )

    monkeypatch.setattr("service.api_server.warm_retriever_if_enabled", _spy)

    class _Retriever:
        enabled = True
        ready = True

    retriever = _Retriever()
    app = create_app(settings=ApiSettings(fuseki_url=None), retriever=retriever)
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200

    assert calls
    assert calls[0][0] is retriever
    assert calls[0][1] is app.state.request_logger
    assert (
        app.state.runtime_state.retriever_runtime.startup_warmup_status == "completed"
    )
    assert (
        app.state.runtime_contract["runtime_state"]["retriever_runtime"][
            "startup_warmup"
        ]["status"]
        == "completed"
    )


def test_shutdown_calls_fuseki_aclose_hook() -> None:
    class _FusekiWithClose:
        def __init__(self) -> None:
            self.closed = False

        async def query(self, template, query):
            return {"head": {"vars": []}, "results": {"bindings": []}}

        async def aclose(self) -> None:
            self.closed = True

    fuseki = _FusekiWithClose()
    app = create_app(settings=ApiSettings(fuseki_url=None), fuseki_client=fuseki)
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
    assert fuseki.closed is True


def test_embedded_fixture_wiring_exposes_default_entity(monkeypatch) -> None:
    monkeypatch.setenv("EARCRAWLER_API_EMBEDDED_FIXTURE", "1")
    app = create_app(settings=ApiSettings(fuseki_url=None))
    gateway_client = app.state.gateway._client  # type: ignore[attr-defined]
    assert gateway_client.__class__.__name__ == "StubFusekiClient"
    assert gateway_client._responses["entity_by_id"][0]["label"] == "Example Entity"


def test_app_factory_preserves_middleware_order() -> None:
    app = create_app(settings=ApiSettings(fuseki_url=None))
    assert [middleware.cls.__name__ for middleware in app.user_middleware] == [
        "RequestContextMiddleware",
        "ConcurrencyLimitMiddleware",
        "BodyLimitMiddleware",
        "ObservabilityMiddleware",
    ]


def test_app_factory_registers_docs_routes_without_schema_pollution() -> None:
    app = create_app(settings=ApiSettings(fuseki_url=None))

    with TestClient(app) as client:
        docs = client.get("/docs")
        openapi_yaml = client.get("/openapi.yaml")
        assert docs.status_code == 200
        assert docs.headers["content-type"].startswith("text/html")
        assert openapi_yaml.status_code == 200
        assert openapi_yaml.headers["content-type"].startswith("application/yaml")

    assert "/docs" not in app.openapi()["paths"]
    assert "/openapi.yaml" not in app.openapi()["paths"]
