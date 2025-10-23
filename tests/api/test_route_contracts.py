from __future__ import annotations

import pytest

pytestmark = pytest.mark.enable_socket


def test_health_endpoint(app) -> None:
    res = app.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "pass"


def test_entity_view_contract(app) -> None:
    res = app.get("/v1/entities/urn:example:entity:1")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "urn:example:entity:1"
    assert "Example Entity" in data["labels"]
    assert any(attr["predicate"].endswith("identifier") for attr in data["attributes"])

    missing = app.get("/v1/entities/urn:missing")
    assert missing.status_code == 404
    err = missing.json()
    assert err["status"] == 404
    assert "trace_id" in err


def test_search_contract(app) -> None:
    res = app.get("/v1/search", params={"q": "example"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 1
    assert payload["results"][0]["score"] == 0.98


def test_sparql_proxy_contract(app) -> None:
    res = app.post(
        "/v1/sparql",
        json={"template": "search_entities", "parameters": {"q": "example", "limit": 1, "offset": 0}},
    )
    assert res.status_code == 200
    payload = res.json()
    assert "head" in payload and "results" in payload


def test_lineage_contract(app) -> None:
    res = app.get("/v1/lineage/urn:example:entity:1")
    assert res.status_code == 200
    payload = res.json()
    assert payload["id"] == "urn:example:entity:1"
    assert payload["edges"]
    assert payload["edges"][0]["relation"].endswith("prov#used") or payload["edges"][0]["relation"].endswith("prov#wasDerivedFrom")
