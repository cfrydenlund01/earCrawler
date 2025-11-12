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


def _load_app(monkeypatch, wrapper_cls):
    monkeypatch.setenv("SPARQL_ENDPOINT_URL", "http://example.com")
    import earCrawler.service.sparql_service as svc

    importlib.reload(svc)
    monkeypatch.setattr(svc, "SPARQLWrapper", wrapper_cls)
    return TestClient(svc.app)


class _GoodWrapper:
    def __init__(self, endpoint: str) -> None:
        self.query_str: str | None = None

    def setQuery(self, q: str) -> None:  # noqa: N802 - API name
        self.query_str = q

    def setReturnFormat(self, fmt: Any) -> None:  # noqa: N802
        self.format = fmt

    class _Result:
        def convert(self) -> dict:
            return {"results": {"bindings": [{"x": {"value": "1"}}]}}

    def query(self) -> "_GoodWrapper._Result":  # noqa: D401
        return self._Result()


class _BadQueryWrapper(_GoodWrapper):
    def query(self):  # noqa: D401,N802 - third-party API
        from SPARQLWrapper.SPARQLExceptions import QueryBadFormed

        raise QueryBadFormed("bad")


class _HttpErrorWrapper(_GoodWrapper):
    def query(self):  # noqa: D401,N802
        raise HTTPError(None, 500, "boom", None, None)


def test_query_success(monkeypatch):
    client = _load_app(monkeypatch, _GoodWrapper)
    resp = client.get("/query", params={"sparql": "SELECT * WHERE {}"})
    assert resp.status_code == 200
    assert resp.json() == {"results": [{"x": {"value": "1"}}]}


def test_query_bad(monkeypatch):
    client = _load_app(monkeypatch, _BadQueryWrapper)
    resp = client.get("/query", params={"sparql": "SELECT bad"})
    assert resp.status_code == 400


def test_query_http_error(monkeypatch):
    client = _load_app(monkeypatch, _HttpErrorWrapper)
    resp = client.get("/query", params={"sparql": "SELECT * WHERE {}"})
    assert resp.status_code == 502


def test_invalid_query(monkeypatch):
    client = _load_app(monkeypatch, _GoodWrapper)
    resp = client.get("/query", params={"sparql": "CONSTRUCT {}"})
    assert resp.status_code == 400


def test_health(monkeypatch):
    client = _load_app(monkeypatch, _GoodWrapper)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
