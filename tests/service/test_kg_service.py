from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))


class _Wrapper:
    def __init__(self, endpoint: str) -> None:
        self.queries: list[str] = []
        self.method: Any | None = None
        self.format: Any | None = None

    def setQuery(self, q: str) -> None:  # noqa: N802
        self.queries.append(q)

    def setReturnFormat(self, fmt: Any) -> None:  # noqa: N802
        self.format = fmt

    def setMethod(self, method: Any) -> None:  # noqa: N802
        self.method = method

    class _Result:
        def convert(self) -> dict:
            return {"results": {"bindings": [{"x": {"value": "1"}}]}}

    def query(self) -> "_Wrapper._Result":  # noqa: D401
        return self._Result()


class _HttpErrorWrapper(_Wrapper):
    def query(self):  # noqa: D401,N802
        raise HTTPError(None, 500, "boom", None, None)


def _load_app(
    monkeypatch,
    wrapper_cls=_Wrapper,
    validate_ret=(True, None, ""),
    parse_ok=True,
):
    monkeypatch.setenv("SPARQL_ENDPOINT_URL", "http://example.com")
    monkeypatch.setenv("SHAPES_FILE_PATH", "shapes.ttl")
    import earCrawler.service.kg_service as svc
    importlib.reload(svc)
    monkeypatch.setattr(svc, "SPARQLWrapper", wrapper_cls)
    monkeypatch.setattr(svc, "validate", lambda **_k: validate_ret)
    if not parse_ok:
        def bad_parse(self, *a, **k):
            raise Exception("parse error")
        monkeypatch.setattr(svc.Graph, "parse", bad_parse)
    else:
        monkeypatch.setattr(svc.Graph, "parse", lambda self, *a, **k: self)
    return TestClient(svc.app)


def test_query_success(monkeypatch):
    client = _load_app(monkeypatch)
    resp = client.post("/kg/query", json={"sparql": "SELECT * WHERE {}"})
    assert resp.status_code == 200
    assert resp.json() == {"results": [{"x": {"value": "1"}}]}


def test_query_invalid(monkeypatch):
    client = _load_app(monkeypatch)
    resp = client.post("/kg/query", json={"sparql": "CONSTRUCT {}"})
    assert resp.status_code == 400


def test_query_http_error(monkeypatch):
    client = _load_app(monkeypatch, wrapper_cls=_HttpErrorWrapper)
    resp = client.post("/kg/query", json={"sparql": "SELECT * WHERE {}"})
    assert resp.status_code == 502


def test_insert_success(monkeypatch):
    client = _load_app(monkeypatch)
    ttl = "<a> <b> <c>."
    resp = client.post("/kg/insert", json={"ttl": ttl})
    assert resp.status_code == 200
    assert resp.json() == {"inserted": True}


def test_insert_shacl_failure(monkeypatch):
    client = _load_app(monkeypatch, validate_ret=(False, None, "bad"))
    resp = client.post("/kg/insert", json={"ttl": "<a> <b> <c>."})
    assert resp.status_code == 400


def test_insert_bad_ttl(monkeypatch):
    client = _load_app(monkeypatch, parse_ok=False)
    resp = client.post("/kg/insert", json={"ttl": "x"})
    assert resp.status_code == 400


def test_insert_http_error(monkeypatch):
    client = _load_app(monkeypatch, wrapper_cls=_HttpErrorWrapper)
    resp = client.post("/kg/insert", json={"ttl": "<a> <b> <c>."})
    assert resp.status_code == 502
