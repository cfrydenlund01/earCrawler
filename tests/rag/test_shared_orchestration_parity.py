from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from pytest_socket import disable_socket, enable_socket, socket_allow_hosts

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import StubFusekiClient
from service.api_server.rag_support import RagQueryCache

from earCrawler.rag import pipeline


class _StubRetriever:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = list(docs)
        self.calls: list[tuple[str, int]] = []
        self.enabled = True
        self.ready = True
        self.failure_type = None
        self.index_path = "stub.faiss"
        self.model_name = "stub-model"

    def query(self, prompt: str, k: int = 5) -> list[dict]:
        self.calls.append((prompt, k))
        return list(self.docs)


@pytest.fixture(autouse=True)
def _allow_socket():
    socket_allow_hosts(["testserver", "localhost"])
    enable_socket()
    yield
    disable_socket()


def _api_client(retriever: _StubRetriever) -> TestClient:
    settings = ApiSettings(fuseki_url=None)
    app = create_app(
        settings,
        fuseki_client=StubFusekiClient({"lineage_by_id": []}),
        retriever=retriever,
        rag_cache=RagQueryCache(ttl_seconds=60, max_entries=4),
    )
    return TestClient(app)


def test_pipeline_and_api_match_temporal_refusal_decision(monkeypatch):
    docs = [
        {
            "id": "urn:entity:future",
            "text": "Future-only rule text.",
            "score": 0.95,
            "source_url": "https://example.org/doc/future",
            "section": "734.3",
            "snapshot_date": "2025-01-01",
            "provider": "federalregister.gov",
        }
    ]

    pipeline_retriever = _StubRetriever(docs)
    api_retriever = _StubRetriever(docs)
    monkeypatch.setattr(
        pipeline,
        "generate_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generation should not run when temporal refusal is active")
        ),
    )

    pipeline_result = pipeline.answer_with_rag(
        "Does this apply?",
        retriever=pipeline_retriever,
        strict_retrieval=False,
        strict_output=True,
        effective_date="2024-06-01",
    )

    api_client = _api_client(api_retriever)
    api_response = api_client.post(
        "/v1/rag/answer",
        json={"query": "Does this apply?", "effective_date": "2024-06-01"},
    )
    api_result = api_response.json()

    assert api_response.status_code == 200
    assert pipeline_result["label"] == api_result["label"] == "unanswerable"
    assert (
        pipeline_result["disabled_reason"]
        == api_result["disabled_reason"]
        == "no_temporally_applicable_evidence"
    )
    assert pipeline_result["retrieval_empty"] is api_result["retrieval_empty"] is True
    assert (
        pipeline_result["retrieval_empty_reason"]
        == api_result["retrieval_empty_reason"]
        == "no_temporally_applicable_evidence"
    )
    assert pipeline_result["output_ok"] is api_result["output_ok"] is True


def test_pipeline_and_api_match_strict_output_schema_error(monkeypatch):
    docs = [
        {
            "id": "urn:entity:1",
            "text": "Example EAR passage text about exports.",
            "score": 0.87,
            "source_url": "https://example.org/doc/1",
            "section": "734.3",
            "provider": "federalregister.gov",
        }
    ]
    pipeline_retriever = _StubRetriever(docs)
    api_retriever = _StubRetriever(docs)

    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    monkeypatch.setenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "1")
    monkeypatch.setattr(pipeline, "generate_chat", lambda *_args, **_kwargs: "freeform")

    import service.api_server.routers.rag as rag_router

    monkeypatch.setattr(rag_router, "generate_chat", lambda *_args, **_kwargs: "freeform")

    pipeline_result = pipeline.answer_with_rag(
        "What is required?",
        retriever=pipeline_retriever,
        strict_retrieval=False,
        strict_output=True,
    )

    api_client = _api_client(api_retriever)
    api_response = api_client.post("/v1/rag/answer", json={"query": "What is required?"})
    api_result = api_response.json()

    assert api_response.status_code == 422
    assert pipeline_result["output_ok"] is False
    assert api_result["output_ok"] is False
    assert pipeline_result["output_error"]["code"] == "invalid_json"
    assert api_result["output_error"]["code"] == "invalid_json"


def test_pipeline_kg_guard_and_api_answer_path_stay_disabled_by_default(monkeypatch):
    docs = [
        {
            "id": "urn:entity:1",
            "text": "Example EAR passage text about exports.",
            "score": 0.87,
            "source_url": "https://example.org/doc/1",
            "section": "734.3",
            "provider": "federalregister.gov",
        }
    ]
    pipeline_retriever = _StubRetriever(docs)
    api_retriever = _StubRetriever(docs)

    monkeypatch.setattr(
        pipeline,
        "expand_with_kg",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("pipeline should not call KG expansion when kg_expansion=False")
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "generate_chat",
        lambda *_args, **_kwargs: (
            "{"
            '"label":"unanswerable",'
            '"answer_text":"Insufficient context.",'
            '"citations":[],'
            '"evidence_okay":{"ok":true,"reasons":["thin_or_empty_retrieval"]},'
            '"assumptions":[]'
            "}"
        ),
    )

    pipeline_result = pipeline.answer_with_rag(
        "Export controls?",
        retriever=pipeline_retriever,
        strict_retrieval=False,
        strict_output=True,
        kg_expansion=False,
        generate=False,
    )

    api_client = _api_client(api_retriever)
    api_response = api_client.post("/v1/rag/answer?generate=0", json={"query": "Export controls?"})
    api_result = api_response.json()

    assert pipeline_result["kg_expansions"] == []
    assert api_response.status_code == 200
    assert api_result["contexts"] == ["[734.3] Example EAR passage text about exports."]
