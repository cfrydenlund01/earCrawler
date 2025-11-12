from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings, RateLimitConfig
from service.api_server.fuseki import StubFusekiClient
from service.api_server.templates import TemplateRegistry


@pytest.fixture(autouse=True)
def _enable_socket(socket_enabled):
    yield


@pytest.fixture()
def app() -> TestClient:
    registry = TemplateRegistry.load_default()
    responses = {
        "entity_by_id": [
            {
                "entity": "urn:example:entity:1",
                "label": "Example Entity",
                "description": "Test entity",
                "type": "http://schema.org/Thing",
                "sameAs": "http://example.com/entity",
                "attribute": "http://purl.org/dc/terms/identifier",
                "value": "ID-001",
            },
            {
                "entity": "urn:example:entity:1",
                "label": "Example Entity",
                "type": "http://schema.org/CreativeWork",
                "attribute": "http://purl.org/dc/terms/created",
                "value": "2023-01-01",
            },
        ],
        "search_entities": [
            {
                "entity": "urn:example:entity:1",
                "label": "Example Entity",
                "score": 0.98,
                "snippet": "Example snippet",
            }
        ],
        "lineage_by_id": [
            {
                "source": "urn:example:entity:1",
                "relation": "http://www.w3.org/ns/prov#used",
                "target": "urn:example:artifact:2",
                "timestamp": {
                    "value": "2023-01-02T00:00:00Z",
                    "datatype": "http://www.w3.org/2001/XMLSchema#dateTime",
                },
            }
        ],
    }

    class FixtureFusekiClient(StubFusekiClient):
        async def query(self, template, query):  # type: ignore[override]
            if template.name == "entity_by_id" and "urn:example:entity:1" not in query:
                return {"head": {"vars": []}, "results": {"bindings": []}}
            return await super().query(template, query)

    client = FixtureFusekiClient(responses=responses)
    settings = ApiSettings(
        fuseki_url=None,
        host="testserver",
        port=9001,
        request_body_limit=32 * 1024,
        request_timeout_seconds=5.0,
        concurrency_limit=4,
        rate_limits=RateLimitConfig(
            anonymous_per_minute=5,
            authenticated_per_minute=10,
            anonymous_burst=2,
            authenticated_burst=4,
        ),
    )
    api = create_app(settings=settings, registry=registry, fuseki_client=client)
    return TestClient(api)
