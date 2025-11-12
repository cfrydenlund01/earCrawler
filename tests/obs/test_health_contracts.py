from __future__ import annotations

from fastapi.testclient import TestClient

import pytest

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import Template, TemplateRegistry


pytestmark = pytest.mark.enable_socket


class FailingFuseki:
    async def query(
        self, template: Template, query: str
    ):  # pragma: no cover - simple stub
        raise RuntimeError("fuseki offline")


@pytest.fixture(autouse=True)
def _enable_socket_fixture(socket_enabled):
    yield


def test_health_endpoint_reports_checks():
    settings = ApiSettings(fuseki_url=None)
    registry = TemplateRegistry.load_default()
    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "pass"
    readiness = payload["readiness"]
    assert readiness["status"] == "pass"
    checks = readiness["checks"]
    assert "fuseki" in checks
    assert checks["fuseki"]["status"] == "pass"
    assert checks["disk"]["status"] in {"pass", "fail"}


def test_health_endpoint_degraded_on_fuseki_failure():
    settings = ApiSettings(fuseki_url=None)
    registry = TemplateRegistry.load_default()
    app = create_app(
        settings=settings, registry=registry, fuseki_client=FailingFuseki()
    )
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["readiness"]["status"] == "fail"
    assert payload["readiness"]["checks"]["fuseki"]["status"] == "fail"
