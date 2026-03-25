from __future__ import annotations

from types import SimpleNamespace

from service.api_server.config import ApiSettings
from service.api_server.rag_support import RagQueryCache
from service.api_server.routers.dependencies import (
    get_limiter,
    get_rag_cache,
    get_retriever,
)
from service.api_server.runtime_state import build_process_local_runtime_state


def test_runtime_state_contract_payload_is_process_local() -> None:
    runtime_state = build_process_local_runtime_state(ApiSettings(fuseki_url=None))

    payload = runtime_state.contract_payload()

    assert payload["backend"] == "process_local"
    assert payload["shared_state_ready"] is False
    assert payload["components"]["rate_limits"] == {
        "storage_scope": "process_local",
        "owner": "runtime_state",
    }
    assert payload["components"]["request_concurrency"] == {
        "storage_scope": "process_local",
        "owner": "runtime_state",
    }
    assert payload["components"]["rag_query_cache"] == {
        "storage_scope": "process_local",
        "owner": "runtime_state",
    }
    assert payload["components"]["retriever_cache"] == {
        "storage_scope": "process_local",
        "owner": "retriever_runtime",
    }
    assert payload["components"]["retriever_warm_state"] == {
        "storage_scope": "process_local",
        "owner": "retriever_runtime",
    }
    assert payload["retriever_runtime"]["cache_storage_scope"] == "process_local"
    assert payload["retriever_runtime"]["warm_state_storage_scope"] == "process_local"
    assert payload["retriever_runtime"]["startup_warmup"]["requested"] is False
    assert payload["retriever_runtime"]["startup_warmup"]["status"] == "not_requested"


def test_dependency_accessors_read_runtime_state() -> None:
    retriever = object()
    runtime_state = build_process_local_runtime_state(
        ApiSettings(fuseki_url=None),
        rag_query_cache=RagQueryCache(ttl_seconds=60, max_entries=4),
        retriever=retriever,  # type: ignore[arg-type]
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                runtime_state=runtime_state,
                rate_limiter=object(),
                rag_cache=object(),
            )
        )
    )

    assert get_limiter(request) is runtime_state.rate_limiter
    assert get_rag_cache(request) is runtime_state.rag_query_cache
    assert get_retriever(request) is runtime_state.retriever_runtime.retriever
