from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


def _import_client():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    module = importlib.import_module("api_clients.tradegov_client")
    importlib.reload(module)
    return module


def test_search_single_page(requests_mock, monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "secret")
    tg = _import_client()
    resp = {"results": [{"id": 1}], "next_page": None}
    m = requests_mock.get("https://api.trade.gov/v1/entities/search", json=resp)
    client = tg.TradeGovEntityClient()
    results = list(client.search_entities("foo"))
    assert results == [{"id": 1}]
    assert m.call_count == 1


def test_search_multi_page(requests_mock, monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "secret")
    tg = _import_client()
    responses = [
        {"json": {"results": [{"id": 1}], "next_page": 2}},
        {"json": {"results": [{"id": 2}], "next_page": None}},
    ]
    m = requests_mock.get("https://api.trade.gov/v1/entities/search", responses)
    client = tg.TradeGovEntityClient()
    results = list(client.search_entities("foo"))
    assert results == [{"id": 1}, {"id": 2}]
    assert m.call_count == 2


def test_client_error(requests_mock, monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "secret")
    tg = _import_client()
    requests_mock.get(
        "https://api.trade.gov/v1/entities/search",
        status_code=404,
        json={"error": "missing"},
    )
    client = tg.TradeGovEntityClient()
    with pytest.raises(tg.TradeGovError):
        list(client.search_entities("foo"))


def test_retries_on_server_error(requests_mock, monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "secret")
    tg = _import_client()
    responses = [
        {"status_code": 500},
        {"status_code": 502},
        {"json": {"results": [{"id": 1}], "next_page": None}},
    ]
    m = requests_mock.get("https://api.trade.gov/v1/entities/search", responses)
    client = tg.TradeGovEntityClient()
    results = list(client.search_entities("foo"))
    assert results == [{"id": 1}]
    assert m.call_count == 3


def test_empty_results(requests_mock, monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "secret")
    tg = _import_client()
    requests_mock.get(
        "https://api.trade.gov/v1/entities/search",
        json={"results": [], "next_page": None},
    )
    client = tg.TradeGovEntityClient()
    results = list(client.search_entities("foo"))
    assert results == []


def test_invalid_json(requests_mock, monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "secret")
    tg = _import_client()
    requests_mock.get(
        "https://api.trade.gov/v1/entities/search",
        text="not json",
        status_code=200,
    )
    client = tg.TradeGovEntityClient()
    with pytest.raises(tg.TradeGovError):
        list(client.search_entities("foo"))


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("TRADEGOV_API_KEY", raising=False)
    tg = _import_client()
    with pytest.raises(RuntimeError):
        tg.TradeGovEntityClient()
