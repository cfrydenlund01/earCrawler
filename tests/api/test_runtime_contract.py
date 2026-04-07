from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import StubFusekiClient
from service.api_server.rag_support import RagQueryCache
from service.api_server.runtime_state import build_process_local_runtime_state


pytestmark = pytest.mark.enable_socket


def test_health_reports_single_host_runtime_contract(app) -> None:
    res = app.get("/health")
    assert res.status_code == 200
    payload = res.json()
    runtime_contract = payload["runtime_contract"]
    assert runtime_contract["topology"] == "single_host"
    assert runtime_contract["declared_instance_count"] == 1
    assert runtime_contract["multi_instance_supported"] is False
    assert runtime_contract["override_active"] is False
    assert runtime_contract["runtime_state"]["backend"] == "process_local"
    assert runtime_contract["runtime_state"]["shared_state_ready"] is False
    assert (
        runtime_contract["runtime_state"]["components"]["rate_limits"]["storage_scope"]
        == "process_local"
    )
    assert (
        runtime_contract["runtime_state"]["components"]["rag_query_cache"][
            "storage_scope"
        ]
        == "process_local"
    )
    assert (
        runtime_contract["runtime_state"]["components"]["request_concurrency"][
            "storage_scope"
        ]
        == "process_local"
    )
    assert (
        runtime_contract["runtime_state"]["components"]["retriever_cache"][
            "storage_scope"
        ]
        == "process_local"
    )
    assert (
        runtime_contract["runtime_state"]["components"]["retriever_warm_state"][
            "storage_scope"
        ]
        == "process_local"
    )
    assert (
        runtime_contract["runtime_state"]["retriever_runtime"]["startup_warmup"][
            "status"
        ]
        == "not_requested"
    )
    assert runtime_contract["process_local_state"]["rate_limits"] == "process_local"
    assert (
        runtime_contract["process_local_state"]["request_concurrency"]
        == "process_local"
    )
    assert runtime_contract["process_local_state"]["rag_query_cache"] == "process_local"
    assert runtime_contract["process_local_state"]["retriever_cache"] == "process_local"
    assert (
        runtime_contract["process_local_state"]["retriever_warm_state"]
        == "process_local"
    )
    assert runtime_contract["capability_registry_schema"] == "capability-registry.v1"
    assert (
        runtime_contract["capability_registry_source"]
        == "service/docs/capability_registry.json"
    )
    capabilities = runtime_contract["capabilities"]
    assert capabilities["api.default_surface"]["status"] == "supported"
    assert capabilities["api.search"]["status"] == "quarantined"
    assert capabilities["retrieval.hybrid"]["status"] == "optional"
    assert capabilities["kg.expansion"]["default_posture"] == "disabled"
    recommendation_inputs = payload["rate_limit_recommendation_inputs"]
    assert recommendation_inputs["status"] == "pass"
    assert recommendation_inputs["schema_version"] == "api-rate-limit-inputs.v1"
    details = recommendation_inputs["details"]
    assert details["total_request_count"] >= 0
    assert "route_classes" in details
    assert "concurrency_gate" in details
    recommendation = payload["rate_limit_recommendation"]
    assert recommendation["status"] == "pass"
    assert recommendation["schema_version"] == "api-rate-limit-recommendation.v1"
    assert recommendation["recommendation_status"] in {
        "ready",
        "insufficient_evidence",
        "unsupported_topology",
    }
    recommendation_details = recommendation["details"]
    assert recommendation_details["operator_override"]["env_vars_authoritative"] is True
    assert "recommendations" in recommendation_details


def test_create_app_rejects_multi_instance_without_override() -> None:
    with pytest.raises(ValueError, match="one API service instance per host"):
        create_app(settings=ApiSettings(fuseki_url=None, declared_instance_count=2))


def test_health_marks_unsupported_multi_instance_override() -> None:
    app = create_app(
        settings=ApiSettings(
            fuseki_url=None,
            declared_instance_count=2,
            allow_unsupported_multi_instance=True,
        ),
        fuseki_client=StubFusekiClient({}),
    )

    with TestClient(app) as client:
        res = client.get("/health")

    assert res.status_code == 200
    payload = res.json()
    runtime_contract = payload["runtime_contract"]
    assert runtime_contract["override_active"] is True
    assert runtime_contract["declared_instance_count"] == 2


def test_create_app_exposes_runtime_state_container() -> None:
    rag_cache = RagQueryCache(ttl_seconds=60, max_entries=4)
    runtime_state = build_process_local_runtime_state(
        ApiSettings(fuseki_url=None),
        rag_query_cache=rag_cache,
    )

    app = create_app(
        settings=ApiSettings(fuseki_url=None),
        fuseki_client=StubFusekiClient({}),
        runtime_state=runtime_state,
    )

    assert app.state.runtime_state is runtime_state
    assert app.state.rate_limiter is runtime_state.rate_limiter
    assert app.state.rag_cache is runtime_state.rag_query_cache
    assert app.state.rag_cache is rag_cache
    assert app.state.rag_retriever is runtime_state.retriever_runtime.retriever


def test_create_app_rejects_conflicting_runtime_state_and_rag_cache() -> None:
    runtime_state = build_process_local_runtime_state(ApiSettings(fuseki_url=None))
    other_cache = RagQueryCache(ttl_seconds=60, max_entries=4)

    with pytest.raises(
        ValueError,
        match="runtime_state and a different rag_cache",
    ):
        create_app(
            settings=ApiSettings(fuseki_url=None),
            fuseki_client=StubFusekiClient({}),
            runtime_state=runtime_state,
            rag_cache=other_cache,
        )


def test_create_app_rejects_conflicting_runtime_state_and_retriever() -> None:
    runtime_state = build_process_local_runtime_state(ApiSettings(fuseki_url=None))

    with pytest.raises(
        ValueError,
        match="runtime_state and a different retriever",
    ):
        create_app(
            settings=ApiSettings(fuseki_url=None),
            fuseki_client=StubFusekiClient({}),
            runtime_state=runtime_state,
            retriever=object(),  # type: ignore[arg-type]
        )
