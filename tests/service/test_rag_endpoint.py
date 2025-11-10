from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from pytest_socket import disable_socket, enable_socket, socket_allow_hosts

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import StubFusekiClient
from service.api_server.rag_support import RagQueryCache


class _StubRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def query(self, prompt: str, k: int = 5) -> list[dict]:
        self.calls.append((prompt, k))
        return [
            {
                "id": "urn:entity:1",
                "text": "Example EAR passage text about exports.",
                "score": 0.87,
                "source_url": "https://example.org/doc/1",
                "section": "734.3",
                "provider": "federalregister.gov",
            }
        ]


def _app(stub_retriever: _StubRetriever) -> TestClient:
    responses = {
        "lineage_by_id": [
            {
                "source": "urn:entity:1",
                "relation": "http://www.w3.org/ns/prov#used",
                "target": "urn:artifact:1",
                "timestamp": "2024-01-01T00:00:00Z",
            }
        ]
    }
    settings = ApiSettings(fuseki_url=None)
    app = create_app(
        settings,
        fuseki_client=StubFusekiClient(responses),
        retriever=stub_retriever,
        rag_cache=RagQueryCache(ttl_seconds=60, max_entries=4),
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _allow_socket():
    socket_allow_hosts(["testserver", "localhost"])
    enable_socket()
    yield
    disable_socket()


def test_rag_endpoint_returns_hits_and_lineage():
    retriever = _StubRetriever()
    client = _app(retriever)

    payload = {"query": "export controls", "include_lineage": True, "top_k": 2}
    resp = client.post("/v1/rag/query", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"]
    assert data["cache"]["hit"] is False
    assert data["results"][0]["source"]["url"] == "https://example.org/doc/1"
    assert data["results"][0]["lineage"]["entity_id"] == "urn:entity:1"
    assert retriever.calls == [("export controls", 2)]

    # Second call should hit the cache.
    resp_cached = client.post("/v1/rag/query", json=payload)
    assert resp_cached.status_code == 200
    assert resp_cached.json()["cache"]["hit"] is True
    assert retriever.calls == [("export controls", 2)]


def test_rag_endpoint_without_lineage():
    retriever = _StubRetriever()
    client = _app(retriever)

    resp = client.post("/v1/rag/query", json={"query": "export controls"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["lineage"] is None
