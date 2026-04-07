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
from service.api_server.middleware import ConcurrencyGate


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
    assert payload["components"]["rate_limit_recommendation_inputs"] == {
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


def test_recommendation_input_snapshot_tracks_pressure_signals() -> None:
    runtime_state = build_process_local_runtime_state(ApiSettings(fuseki_url=None))
    collector = runtime_state.rate_limit_recommendation_inputs
    collector.record(
        route_class="query",
        status_code=200,
        latency_ms=40.0,
        concurrency_saturated=False,
    )
    collector.record(
        route_class="query",
        status_code=429,
        latency_ms=60.0,
        concurrency_saturated=True,
    )
    collector.record(
        route_class="answer",
        status_code=503,
        latency_ms=150.0,
        concurrency_saturated=True,
    )

    payload = runtime_state.recommendation_inputs_payload()
    route_classes = payload["route_classes"]

    query = route_classes["query"]
    assert query["request_count"] == 2
    assert query["status_429_count"] == 1
    assert query["status_503_count"] == 0
    assert query["rate_429"] == 0.5
    assert query["concurrency_saturated_count"] == 1
    assert query["concurrency_saturation_rate"] == 0.5
    assert query["p95_latency_ms"] == 60.0

    answer = route_classes["answer"]
    assert answer["request_count"] == 1
    assert answer["status_503_count"] == 1
    assert answer["rate_503"] == 1.0
    assert answer["concurrency_saturated_count"] == 1

    assert payload["total_request_count"] == 3
    assert payload["concurrency_gate"]["saturation_rate"] == 0.0


def test_concurrency_gate_saturation_snapshot_counts_attempts() -> None:
    gate = ConcurrencyGate(limit=1)

    async def _scenario() -> None:
        assert gate.mark_attempt() is False
        async with gate:
            assert gate.mark_attempt() is True

    import asyncio

    asyncio.run(_scenario())
    snapshot = gate.saturation_snapshot()
    assert snapshot["attempt_count"] == 2
    assert snapshot["saturated_count"] == 1
    assert snapshot["saturation_rate"] == 0.5
