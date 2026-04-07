from __future__ import annotations

from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings, RateLimitConfig
from service.api_server.fuseki import StubFusekiClient
from service.api_server.rag_support import NullRetriever


def test_middleware_records_rate_limit_recommendation_inputs() -> None:
    settings = ApiSettings(
        fuseki_url=None,
        host="testserver",
        port=9001,
        request_body_limit=32 * 1024,
        request_timeout_seconds=5.0,
        concurrency_limit=4,
        enable_search=True,
        rate_limits=RateLimitConfig(
            anonymous_per_minute=2,
            authenticated_per_minute=4,
            anonymous_burst=2,
            authenticated_burst=4,
        ),
    )
    app = create_app(
        settings=settings,
        fuseki_client=StubFusekiClient({}),
        retriever=NullRetriever(reason="disabled for telemetry test"),
    )

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/v1/rag/query", json={"query": "export control"}).status_code == 503
        assert client.get("/v1/search", params={"q": "export"}).status_code == 200
        assert client.get("/v1/search", params={"q": "export"}).status_code == 200
        assert client.get("/v1/search", params={"q": "export"}).status_code == 429

    payload = app.state.runtime_state.recommendation_inputs_payload()
    route_classes = payload["route_classes"]
    health = route_classes["health"]
    query = route_classes["query"]

    assert health["request_count"] == 1
    assert query["request_count"] == 4
    assert query["status_429_count"] == 1
    assert query["status_503_count"] == 1
    assert query["rate_429"] == 0.25
    assert query["rate_503"] == 0.25
    assert query["p95_latency_ms"] >= 0.0
    assert query["concurrency_saturation_rate"] == 0.0
    assert payload["total_request_count"] == 5
