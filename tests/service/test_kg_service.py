from __future__ import annotations

import importlib
from typing import Any
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient
from pytest_socket import disable_socket, enable_socket, socket_allow_hosts


@pytest.fixture(autouse=True)
def _allow_socket():
    socket_allow_hosts(["testserver", "localhost"])
    enable_socket()
    yield
    disable_socket()


class _GoodWrapper:
    def __init__(self, endpoint: str) -> None:
        self.query_str: str | None = None
        self.method: str | None = None

    def setQuery(self, q: str) -> None:  # noqa: N802 - external API
        self.query_str = q

    def setReturnFormat(self, fmt: Any) -> None:  # noqa: N802 - external API
        self.format = fmt

    def setMethod(self, method: str) -> None:  # noqa: N802 - external API
        self.method = method

    class _Result:
        def convert(self) -> dict:
            return {"results": {"bindings": [{"x": {"value": "1"}}]}}

    def query(self):  # noqa: D401 - external API
        return self._Result()


class _HttpErrorWrapper(_GoodWrapper):
    def query(self):  # noqa: D401,N802
        raise HTTPError(None, 500, "boom", None, None)


def _load_app(monkeypatch, wrapper_cls, validate_func, tmp_path) -> TestClient:
    shapes_file = tmp_path / "shapes.ttl"
    shapes_file.write_text("@prefix ex: <http://example.org/> .", encoding="utf-8")

    monkeypatch.setenv("SPARQL_ENDPOINT_URL", "http://example.com")
    monkeypatch.setenv("SHAPES_FILE_PATH", str(shapes_file))

    import earCrawler.service.kg_service as svc
    importlib.reload(svc)
    monkeypatch.setattr(svc, "SPARQLWrapper", wrapper_cls)
    monkeypatch.setattr(svc, "validate", validate_func)
    return TestClient(svc.app)


def test_query_success(monkeypatch, tmp_path):
    client = _load_app(monkeypatch, _GoodWrapper, lambda **_: (True, None, ""), tmp_path)
    resp = client.post("/kg/query", json={"sparql": "SELECT * WHERE {}"})
    assert resp.status_code == 200
    assert resp.json() == {"results": [{"x": {"value": "1"}}]}


def test_query_invalid(monkeypatch, tmp_path):
    client = _load_app(monkeypatch, _GoodWrapper, lambda **_: (True, None, ""), tmp_path)
    resp = client.post("/kg/query", json={"sparql": "CONSTRUCT {}"})
    assert resp.status_code == 400


def test_query_http_error(monkeypatch, tmp_path):
    client = _load_app(monkeypatch, _HttpErrorWrapper, lambda **_: (True, None, ""), tmp_path)
    resp = client.post("/kg/query", json={"sparql": "SELECT * WHERE {}"})
    assert resp.status_code == 502


def test_insert_success(monkeypatch, tmp_path):
    validate_ok = lambda **_: (True, None, "")
    client = _load_app(monkeypatch, _GoodWrapper, validate_ok, tmp_path)
    resp = client.post("/kg/insert", json={"ttl": "<a> <b> <c> ."})
    assert resp.status_code == 200
    assert resp.json() == {"inserted": True}


def test_insert_validation_error(monkeypatch, tmp_path):
    validate_bad = lambda **_: (False, None, "bad")
    client = _load_app(monkeypatch, _GoodWrapper, validate_bad, tmp_path)
    resp = client.post("/kg/insert", json={"ttl": "<a> <b> <c> ."})
    assert resp.status_code == 400
    assert "bad" in resp.text


def test_insert_http_error(monkeypatch, tmp_path):
    validate_ok = lambda **_: (True, None, "")
    client = _load_app(monkeypatch, _HttpErrorWrapper, validate_ok, tmp_path)
    resp = client.post("/kg/insert", json={"ttl": "<a> <b> <c> ."})
    assert resp.status_code == 502


def test_health(monkeypatch, tmp_path):
    client = _load_app(monkeypatch, _GoodWrapper, lambda **_: (True, None, ""), tmp_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
