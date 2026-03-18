from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import StubFusekiClient
from service.api_server.templates import TemplateRegistry


pytestmark = pytest.mark.enable_socket


def test_search_route_is_disabled_by_default() -> None:
    settings = ApiSettings(fuseki_url=None)
    app = create_app(
        settings=settings,
        registry=TemplateRegistry.load_default(),
        fuseki_client=StubFusekiClient(
            responses={
                "search_entities": [
                    {
                        "entity": "urn:example:entity:1",
                        "label": "Example Entity",
                        "score": 0.98,
                        "snippet": "Example snippet",
                    }
                ]
            }
        ),
    )
    client = TestClient(app)

    res = client.get("/v1/search", params={"q": "example"})
    assert res.status_code == 404


def test_search_route_can_be_enabled_explicitly() -> None:
    settings = ApiSettings(fuseki_url=None, enable_search=True)
    app = create_app(
        settings=settings,
        registry=TemplateRegistry.load_default(),
        fuseki_client=StubFusekiClient(
            responses={
                "search_entities": [
                    {
                        "entity": "urn:example:entity:1",
                        "label": "Example Entity",
                        "score": 0.98,
                        "snippet": "Example snippet",
                    }
                ]
            }
        ),
    )
    client = TestClient(app)

    res = client.get("/v1/search", params={"q": "example"})
    assert res.status_code == 200


def test_search_gate_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EARCRAWLER_API_ENABLE_SEARCH", raising=False)
    assert ApiSettings.from_env().enable_search is False

    monkeypatch.setenv("EARCRAWLER_API_ENABLE_SEARCH", "1")
    assert ApiSettings.from_env().enable_search is True
