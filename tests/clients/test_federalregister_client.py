from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api_clients.federalregister_client import FederalRegisterClient, FederalRegisterError
from earCrawler.utils import budget


def test_get_ear_articles(recorder):
    client = FederalRegisterClient()
    with recorder.use_cassette("federalregister_get_ear_articles.yaml"):
        articles = client.get_ear_articles("export", per_page=1)
    assert len(articles) == 1
    art = articles[0]
    assert art["id"] == "2023-12345"
    assert art["title"]
    assert art["text"] == "Hello world."


def test_get_article_text(recorder):
    client = FederalRegisterClient()
    with recorder.use_cassette("federalregister_get_article_text.yaml"):
        text = client.get_article_text("2023-12345")
    assert text == "Hello world."


def test_federalregister_budget(monkeypatch):
    class DummyResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        text = "{}"

        def json(self):
            return {}

        def raise_for_status(self):
            return None

    monkeypatch.setenv("FR_MAX_CALLS", "1")
    budget.reset("federalregister")
    client = FederalRegisterClient()
    monkeypatch.setattr(client.cache, "get", lambda *args, **kwargs: DummyResponse())
    client._get_json("url", {})
    with pytest.raises(budget.BudgetExceededError):
        client._get_json("url", {})
    budget.reset("federalregister")


def test_get_ear_articles_no_results_sets_status(monkeypatch):
    client = FederalRegisterClient()
    monkeypatch.setattr(client, "_get_json", lambda *args, **kwargs: {"results": []})
    results = client.get_ear_articles("nothing", per_page=1)
    assert results == []
    status = client.get_last_status("get_ear_articles")
    assert status is not None
    assert status.state == "no_results"


def test_get_ear_articles_invalid_response_sets_status(monkeypatch):
    client = FederalRegisterClient()

    def _boom(*args, **kwargs):
        raise FederalRegisterError("invalid payload")

    monkeypatch.setattr(client, "_get_json", _boom)
    results = client.get_ear_articles("export", per_page=1)
    assert results == []
    status = client.get_last_status("get_ear_articles")
    assert status is not None
    assert status.state == "invalid_response"


def test_get_ear_articles_retry_exhausted_sets_status(monkeypatch):
    client = FederalRegisterClient()

    def _boom(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(client, "_get_json", _boom)
    results = client.get_ear_articles("export", per_page=1)
    assert results == []
    status = client.get_last_status("get_ear_articles")
    assert status is not None
    assert status.state == "retry_exhausted"


def test_search_documents_result_includes_typed_status(monkeypatch):
    client = FederalRegisterClient()
    monkeypatch.setattr(client, "_get_json", lambda *args, **kwargs: {"results": []})
    result = client.search_documents_result("export", per_page=5)
    assert result.data == []
    assert result.state == "no_results"
    assert result.degraded is False


def test_get_document_result_propagates_invalid_response(monkeypatch):
    client = FederalRegisterClient()

    def _boom(*args, **kwargs):
        raise FederalRegisterError("bad json", state="invalid_response")

    monkeypatch.setattr(client, "_get_json", _boom)
    result = client.get_document_result("2023-99999")
    assert result.data == {}
    assert result.state == "invalid_response"
