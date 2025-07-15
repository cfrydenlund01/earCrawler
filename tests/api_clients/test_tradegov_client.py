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
        assert name == "TRADEGOV_API_KEY"
        if api_key is None:
            raise Exception("missing")
        return {"CredentialBlob": api_key.encode("utf-16")}

    module.CredRead = cred_read
    sys.modules["win32cred"] = module
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    tg = importlib.import_module("api_clients.tradegov_client")
    importlib.reload(tg)
    return tg


def test_search_single_page(requests_mock):
    tg = _import_client("secret")
    resp = {"results": [{"id": 1}], "next_page": None}
    m = requests_mock.get("https://api.trade.gov/v1/entities/search", json=resp)
    client = tg.TradeGovClient()
    results = list(client.search_entities("foo"))
    assert results == [{"id": 1}]
    assert m.call_count == 1


def test_search_multi_page(requests_mock):
    tg = _import_client("secret")
    responses = [
        {"json": {"results": [{"id": 1}], "next_page": 2}},
        {"json": {"results": [{"id": 2}], "next_page": None}},
    ]
    m = requests_mock.get("https://api.trade.gov/v1/entities/search", responses)
    client = tg.TradeGovClient()
    results = list(client.search_entities("foo"))
    assert results == [{"id": 1}, {"id": 2}]
    assert m.call_count == 2


def test_client_error(requests_mock):
    tg = _import_client("secret")
    requests_mock.get(
        "https://api.trade.gov/v1/entities/search",
        status_code=404,
        json={"error": "missing"},
    )
    client = tg.TradeGovClient()
    with pytest.raises(tg.TradeGovError):
        list(client.search_entities("foo"))


def test_retries_on_server_error(requests_mock):
    tg = _import_client("secret")
    responses = [
        {"status_code": 500},
        {"status_code": 502},
        {"json": {"results": [{"id": 1}], "next_page": None}},
    ]
    m = requests_mock.get("https://api.trade.gov/v1/entities/search", responses)
    client = tg.TradeGovClient()
    results = list(client.search_entities("foo"))
    assert results == [{"id": 1}]
    assert m.call_count == 3


def test_empty_results(requests_mock):
    tg = _import_client("secret")
    requests_mock.get(
        "https://api.trade.gov/v1/entities/search",
        json={"results": [], "next_page": None},
    )
    client = tg.TradeGovClient()
    results = list(client.search_entities("foo"))
    assert results == []


def test_invalid_json(requests_mock):
    tg = _import_client("secret")
    requests_mock.get(
        "https://api.trade.gov/v1/entities/search",
        text="not json",
        status_code=200,
    )
    client = tg.TradeGovClient()
    with pytest.raises(tg.TradeGovError):
        list(client.search_entities("foo"))


def test_missing_api_key():
    tg = _import_client(None)
    with pytest.raises(RuntimeError):
        tg.TradeGovClient()
