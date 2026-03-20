from __future__ import annotations

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api_clients.tradegov_client import TradeGovClient, TradeGovError
from earCrawler.utils import budget


@pytest.mark.usefixtures("recorder")
def test_lookup_entity(monkeypatch, recorder):
    monkeypatch.setenv("TRADEGOV_API_KEY", "DUMMY")
    client = TradeGovClient()
    with recorder.use_cassette("tradegov_lookup_entity.yaml"):
        rec = client.lookup_entity("ACME Corp")
    assert rec["id"] == "E123"
    assert rec["name"] == "Acme Corp"
    assert rec["country"] == "US"
    assert rec["source_url"].startswith("https://")


@pytest.mark.usefixtures("recorder")
def test_search(monkeypatch, recorder):
    monkeypatch.setenv("TRADEGOV_API_KEY", "DUMMY")
    client = TradeGovClient()
    with recorder.use_cassette("tradegov_search.yaml"):
        results = client.search("ACME", limit=2)
    assert len(results) == 2
    assert results[0]["id"] == "E1"


def test_budget_limit(monkeypatch):
    class DummyResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        text = "{}"

        def json(self):
            return {}

        def raise_for_status(self):
            return None

    monkeypatch.setenv("TRADEGOV_API_KEY", "DUMMY")
    monkeypatch.setenv("TRADEGOV_MAX_CALLS", "1")
    budget.reset("tradegov")
    client = TradeGovClient()
    monkeypatch.setattr(client.cache, "get", lambda *args, **kwargs: DummyResponse())
    client._get("/search", {"name": "foo"})
    with pytest.raises(budget.BudgetExceededError):
        client._get("/search", {"name": "foo"})
    budget.reset("tradegov")


def test_search_missing_credentials_sets_status(monkeypatch):
    monkeypatch.setattr("api_clients.tradegov_client.get_secret", lambda *_, **__: "")
    client = TradeGovClient()
    results = client.search("ACME", limit=2)
    assert results == []
    status = client.get_last_status("search")
    assert status is not None
    assert status.state == "missing_credentials"


def test_search_invalid_response_sets_status(monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "DUMMY")
    client = TradeGovClient()

    def _boom(*args, **kwargs):
        raise TradeGovError("bad payload", state="invalid_response")

    monkeypatch.setattr(client, "_get", _boom)
    results = client.search("ACME", limit=2)
    assert results == []
    status = client.get_last_status("search")
    assert status is not None
    assert status.state == "invalid_response"


def test_search_result_includes_typed_status(monkeypatch):
    monkeypatch.setattr("api_clients.tradegov_client.get_secret", lambda *_, **__: "")
    client = TradeGovClient()
    result = client.search_result("ACME", limit=2)
    assert result.data == []
    assert result.state == "missing_credentials"
    assert result.degraded is True


def test_lookup_entity_result_propagates_failure_state(monkeypatch):
    monkeypatch.setenv("TRADEGOV_API_KEY", "DUMMY")
    client = TradeGovClient()

    def _boom(*args, **kwargs):
        raise TradeGovError("bad payload", state="invalid_response")

    monkeypatch.setattr(client, "_get", _boom)
    result = client.lookup_entity_result("ACME")
    assert result.data == {}
    assert result.state == "invalid_response"
