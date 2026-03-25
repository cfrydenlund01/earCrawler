from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pytest_socket import disable_socket, enable_socket, socket_allow_hosts

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import StubFusekiClient
from service.api_server.rag_support import RagQueryCache, NullRetriever, BrokenRetriever


class _StubRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.enabled = True
        self.ready = True
        self.failure_type = None
        self.index_path = "stub.faiss"
        self.model_name = "stub-model"

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
    assert data["retrieval_empty"] is False
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
    assert data["retrieval_empty"] is False


def test_rag_query_offloads_retriever_to_thread(monkeypatch):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    offload_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        offload_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(rag_router.asyncio, "to_thread", _fake_to_thread)

    resp = client.post("/v1/rag/query", json={"query": "export controls", "top_k": 2})
    assert resp.status_code == 200
    assert any(
        getattr(func, "__name__", "") in {"query", "run_retrieval_sync"}
        for func, _, _ in offload_calls
    )


def test_llm_endpoint_disabled_returns_stub(monkeypatch):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    called = {"value": False}

    def _fail(_messages, *a, **k):
        called["value"] = True
        raise rag_router.LLMProviderError("disabled")

    monkeypatch.setattr(rag_router, "generate_chat", _fail)

    resp = client.post("/v1/rag/answer", json={"query": "export controls"})
    assert resp.status_code == 503
    data = resp.json()
    assert data["rag_enabled"] is True
    assert data["llm_enabled"] is False
    assert data["disabled_reason"]
    assert data["output_ok"] is False
    assert called["value"] is False
    assert data["egress"]["remote_enabled"] is False
    assert data["egress"]["disabled_reason"]
    assert "prompt_hash" in data["egress"]
    assert "context_hashes" in data["egress"]


def test_llm_endpoint_offloads_generate_to_thread(monkeypatch):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    def _stub_generate(_messages, *a, **k):
        return (
            "{"
            '"label":"permitted",'
            '"answer_text":"offloaded answer",'
            '"citations":[{"section_id":"EAR-734.3","quote":"Example EAR passage text about exports.","span_id":""}],'
            '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
            '"assumptions":[]'
            "}"
        )

    offload_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        offload_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(rag_router, "generate_chat", _stub_generate)
    monkeypatch.setattr(rag_router.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")

    resp = client.post("/v1/rag/answer", json={"query": "export controls", "top_k": 2})
    assert resp.status_code == 200
    assert any(
        getattr(func, "__name__", "") in {"query", "run_retrieval_sync"}
        for func, _, _ in offload_calls
    )
    assert any(func is _stub_generate for func, _, _ in offload_calls)


def test_llm_endpoint_returns_answer_and_contexts(monkeypatch):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    monkeypatch.setattr(
        rag_router,
        "generate_chat",
        lambda _messages, *a, **k: (
            '{'
            '"label":"permitted",'
            '"answer_text":"stubbed answer",'
            '"citations":[{"section_id":"EAR-734.3","quote":"Example EAR passage text about exports.","span_id":""}],'
            '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
            '"assumptions":[]'
            '}'
        ),
    )
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")

    resp = client.post("/v1/rag/answer", json={"query": "export controls", "top_k": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "stubbed answer"
    assert data["label"] == "permitted"
    assert "Example EAR passage text about exports." in (data.get("justification") or "")
    assert data["output_ok"] is True
    assert data["output_error"] is None
    assert data["citations"][0]["section_id"] == "EAR-734.3"
    assert data["citations"][0]["quote"] == "Example EAR passage text about exports."
    assert data["evidence_okay"]["ok"] is True
    assert data["assumptions"] == []
    assert data["contexts"] == ["[734.3] Example EAR passage text about exports."]
    assert data["retrieved"][0]["url"] == "https://example.org/doc/1"
    assert data["retrieval_empty"] is False
    assert data["egress"]["remote_enabled"] is True
    assert data["egress"]["provider"] == "groq"
    assert data["egress"]["model"]
    assert data["egress"]["redaction_mode"] == "none"
    assert len(data["egress"]["prompt_hash"]) == 64
    assert len(data["egress"]["context_hashes"]) == 1
    assert len(data["egress"]["context_hashes"][0]) == 64
    assert "export controls" not in str(data["egress"])
    assert "Example EAR passage text about exports." not in str(data["egress"])


def test_llm_endpoint_supports_local_adapter_without_remote_egress(
    monkeypatch,
    tmp_path,
):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router
    from earCrawler.rag import llm_runtime

    run_dir = tmp_path / "phase5-run"
    adapter_dir = run_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (run_dir / "run_metadata.json").write_text("{}", encoding="utf-8")
    (run_dir / "inference_smoke.json").write_text(
        json.dumps({"base_model": "Qwen/Qwen2.5-7B-Instruct"}),
        encoding="utf-8",
    )

    called = {"remote": False}

    def _fail_remote(_messages, *a, **k):
        called["remote"] = True
        raise AssertionError("generate_chat should not run for local adapter path")

    monkeypatch.setattr(rag_router, "generate_chat", _fail_remote)
    monkeypatch.setattr(
        llm_runtime,
        "generate_local_chat",
        lambda *_args, **_kwargs: (
            '{'
            '"label":"permitted",'
            '"answer_text":"local adapter answer",'
            '"justification":"Example EAR passage text about exports.",'
            '"citations":[{"section_id":"EAR-734.3","quote":"Example EAR passage text about exports.","span_id":""}],'
            '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
            '"assumptions":[]'
            '}'
        ),
    )
    monkeypatch.setenv("LLM_PROVIDER", "local_adapter")
    monkeypatch.setenv("EARCRAWLER_ENABLE_LOCAL_LLM", "1")
    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_ADAPTER_DIR", str(adapter_dir))
    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_MODEL_ID", "phase5-run")
    monkeypatch.setenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "1")

    resp = client.post("/v1/rag/answer", json={"query": "export controls", "top_k": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert called["remote"] is False
    assert data["answer"] == "local adapter answer"
    assert data["provider"] == "local_adapter"
    assert data["model"] == "phase5-run"
    assert data["llm_enabled"] is True
    assert data["egress"]["remote_enabled"] is False


def test_llm_endpoint_retrieval_only_skips_generation(monkeypatch):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("generate_chat should not be called for retrieval-only path")

    monkeypatch.setattr(rag_router, "generate_chat", _fail_if_called)

    resp = client.post("/v1/rag/answer?generate=0", json={"query": "export controls"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rag_enabled"] is True
    assert data["llm_enabled"] is False
    assert data["disabled_reason"] == "generation_disabled_by_request"
    assert data["answer"] is None
    assert data["retrieved"]
    assert data["contexts"] == ["[734.3] Example EAR passage text about exports."]
    assert data["egress"]["remote_enabled"] is False
    assert data["egress"]["disabled_reason"] == "generation_disabled_by_request"


def test_rag_query_filters_results_by_effective_date():
    class _TemporalRetriever(_StubRetriever):
        def query(self, prompt: str, k: int = 5) -> list[dict]:
            self.calls.append((prompt, k))
            return [
                {
                    "id": "urn:entity:future",
                    "text": "Future rule text.",
                    "score": 0.95,
                    "source_url": "https://example.org/doc/future",
                    "section": "734.3",
                    "snapshot_date": "2025-01-01",
                    "provider": "federalregister.gov",
                },
                {
                    "id": "urn:entity:current",
                    "text": "Rule applicable in 2024.",
                    "score": 0.90,
                    "source_url": "https://example.org/doc/current",
                    "section": "734.3",
                    "snapshot_date": "2024-01-01",
                    "provider": "federalregister.gov",
                },
            ]

    retriever = _TemporalRetriever()
    client = _app(retriever)

    resp = client.post(
        "/v1/rag/query",
        json={"query": "export controls", "effective_date": "2024-06-01", "top_k": 1},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_empty"] is False
    assert data["results"][0]["content"] == "Rule applicable in 2024."
    assert retriever.calls[0][1] >= 12


def test_llm_endpoint_refuses_when_temporal_evidence_is_not_applicable(monkeypatch):
    class _TemporalRetriever(_StubRetriever):
        def query(self, prompt: str, k: int = 5) -> list[dict]:
            self.calls.append((prompt, k))
            return [
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

    retriever = _TemporalRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    called = {"value": False}

    def _fail(_messages, *a, **k):
        called["value"] = True
        raise AssertionError("generate_chat should not run for temporal refusal")

    monkeypatch.setattr(rag_router, "generate_chat", _fail)

    resp = client.post(
        "/v1/rag/answer",
        json={"query": "export controls", "effective_date": "2024-06-01"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "unanswerable"
    assert data["disabled_reason"] == "no_temporally_applicable_evidence"
    assert data["retrieval_empty"] is True
    assert data["retrieval_empty_reason"] == "no_temporally_applicable_evidence"
    assert data["output_ok"] is True
    assert called["value"] is False


def test_warmup_skips_when_retriever_unavailable(monkeypatch):
    monkeypatch.setenv("EARCRAWLER_WARM_RETRIEVER", "1")
    monkeypatch.setenv("EARCRAWLER_WARM_RETRIEVER_TIMEOUT_SECONDS", "1")
    broken = BrokenRetriever(
        RuntimeError("missing sentence-transformers"),
        failure_type="retriever_unavailable",
    )
    responses = {"lineage_by_id": []}
    settings = ApiSettings(fuseki_url=None)
    app = create_app(
        settings,
        fuseki_client=StubFusekiClient(responses),
        retriever=broken,
        rag_cache=RagQueryCache(ttl_seconds=60, max_entries=4),
    )
    events: list[str] = []
    original_info = app.state.request_logger.info

    def _capture(event: str, **fields):
        events.append(event)
        return original_info(event, **fields)

    app.state.request_logger.info = _capture  # type: ignore[method-assign]
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert (
            health.json()["runtime_contract"]["runtime_state"]["retriever_runtime"][
                "startup_warmup"
            ]["status"]
            == "skipped"
        )
        assert (
            health.json()["runtime_contract"]["runtime_state"]["retriever_runtime"][
                "startup_warmup"
            ]["reason"]
            == "retriever_unavaila"
        )

    assert "rag.warmup.skipped" in events


def test_rag_query_returns_503_when_disabled():
    client = _app(NullRetriever())
    resp = client.post("/v1/rag/query", json={"query": "export controls"})
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == 503


def test_rag_answer_returns_503_when_retriever_broken():
    broken = BrokenRetriever(RuntimeError("index missing"), failure_type="index_missing")
    client = _app(broken)
    resp = client.post("/v1/rag/answer", json={"query": "export controls"})
    assert resp.status_code == 503
    data = resp.json()
    assert data["rag_enabled"] is True
    assert data["retrieval_empty"] is True
    assert data["retrieval_empty_reason"] == "index_missing"
    assert "index missing" in (data.get("disabled_reason") or "")
    assert data["output_ok"] is False
    assert data["egress"]["remote_enabled"] is False


def test_rag_answer_marks_no_hits(monkeypatch):
    class _EmptyRetriever(_StubRetriever):
        def query(self, prompt: str, k: int = 5) -> list[dict]:
            self.calls.append((prompt, k))
            return []

    retriever = _EmptyRetriever()
    monkeypatch.setattr(
        "service.api_server.routers.rag.generate_chat",
        lambda _messages, *a, **k: (
            '{'
            '"label":"unanswerable",'
            '"answer_text":"Insufficient context to determine. Need ECCN, destination, and end-use.",'
            '"citations":[],'
            '"evidence_okay":{"ok":true,"reasons":["no_grounded_quote_for_key_claim"]},'
            '"assumptions":[]'
            '}'
        ),
    )
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    client = _app(retriever)
    resp = client.post("/v1/rag/answer", json={"query": "export controls"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_empty"] is True
    assert data["retrieval_empty_reason"] == "no_hits"


def test_llm_endpoint_schema_failure_returns_422(monkeypatch):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    monkeypatch.setattr(
        rag_router, "generate_chat", lambda _messages, *a, **k: "freeform answer"
    )
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")

    resp = client.post("/v1/rag/answer", json={"query": "export controls"})
    assert resp.status_code == 422
    data = resp.json()
    assert data["output_ok"] is False
    assert data["output_error"]["code"] == "invalid_json"
    assert data["answer"] is None
    assert data["egress"]["remote_enabled"] is True


def test_llm_endpoint_ungrounded_quote_returns_422(monkeypatch):
    retriever = _StubRetriever()
    client = _app(retriever)

    import service.api_server.routers.rag as rag_router

    monkeypatch.setattr(
        rag_router,
        "generate_chat",
        lambda _messages, *a, **k: (
            '{'
            '"label":"permitted",'
            '"answer_text":"stubbed answer",'
            '"citations":[{"section_id":"EAR-734.3","quote":"NOT IN CONTEXT","span_id":""}],'
            '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
            '"assumptions":[]'
            '}'
        ),
    )
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")

    resp = client.post("/v1/rag/answer", json={"query": "export controls"})
    assert resp.status_code == 422
    data = resp.json()
    assert data["output_ok"] is False
    assert data["output_error"]["code"] == "ungrounded_citation"
    assert data["egress"]["remote_enabled"] is True
