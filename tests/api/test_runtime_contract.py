from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import StubFusekiClient


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
    assert runtime_contract["process_local_state"]["rate_limits"] == "process_local"
    assert runtime_contract["process_local_state"]["rag_query_cache"] == "process_local"
    assert runtime_contract["process_local_state"]["retriever_cache"] == "process_local"
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
