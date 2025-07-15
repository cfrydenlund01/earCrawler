from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


def _import_client(api_key: str | None):
    module = types.SimpleNamespace()
    module.CRED_TYPE_GENERIC = 1

    def cred_read(name: str, cred_type: int, flags: int):
        assert name == "FEDREGISTER_API_KEY"
        if api_key is None:
            raise Exception("missing")
        return {"CredentialBlob": api_key.encode("utf-16")}

    module.CredRead = cred_read
    sys.modules["win32cred"] = module
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    fr = importlib.import_module("api_clients.federalregister_client")
    importlib.reload(fr)
    return fr


def test_search_single_page(requests_mock):
    fr = _import_client("secret")
    resp = {"results": [{"id": 1}]}
    m = requests_mock.get(
        "https://api.federalregister.gov/v1/documents",
        json=resp,
    )
    client = fr.FederalRegisterClient()
    results = list(client.search_documents("foo"))
    assert results == [{"id": 1}]
    assert m.call_count == 1


def test_search_multi_page(requests_mock):
    fr = _import_client("secret")
    responses = [
        {"json": {"results": [{"id": 1}]}},
        {"json": {"results": [{"id": 2}]}},
        {"json": {"results": []}},
    ]
    m = requests_mock.get(
        "https://api.federalregister.gov/v1/documents",
        responses,
    )
    client = fr.FederalRegisterClient()
    results = list(client.search_documents("foo", per_page=1))
    assert results == [{"id": 1}, {"id": 2}]
    assert m.call_count == 3


def test_client_error(requests_mock):
    fr = _import_client("secret")
    requests_mock.get(
        "https://api.federalregister.gov/v1/documents",
        status_code=404,
        text="missing",
    )
    client = fr.FederalRegisterClient()
    with pytest.raises(fr.FederalRegisterError):
        list(client.search_documents("foo"))


def test_retries_on_server_error(requests_mock, monkeypatch):
    fr = _import_client("secret")
    responses = [
        {"status_code": 500},
        {"status_code": 502},
        {"json": {"results": []}},
    ]
    m = requests_mock.get(
        "https://api.federalregister.gov/v1/documents",
        responses,
    )
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    client = fr.FederalRegisterClient()
    results = list(client.search_documents("foo"))
    assert results == []
    assert m.call_count == 3
    assert sleeps == [1, 2]


def test_empty_results(requests_mock):
    fr = _import_client("secret")
    requests_mock.get(
        "https://api.federalregister.gov/v1/documents",
        json={"results": []},
    )
    client = fr.FederalRegisterClient()
    results = list(client.search_documents("foo"))
    assert results == []


def test_invalid_json(requests_mock):
    fr = _import_client("secret")
    requests_mock.get(
        "https://api.federalregister.gov/v1/documents",
        text="not json",
        status_code=200,
    )
    client = fr.FederalRegisterClient()
    with pytest.raises(fr.FederalRegisterError):
        list(client.search_documents("foo"))


def test_missing_api_key():
    fr = _import_client(None)
    with pytest.raises(RuntimeError):
        fr.FederalRegisterClient()
