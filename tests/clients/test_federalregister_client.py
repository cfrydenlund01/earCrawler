from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.utils import budget


def test_get_ear_articles(recorder):
    client = FederalRegisterClient()
    with recorder.use_cassette("federalregister_get_ear_articles.yaml"):
        articles = client.get_ear_articles("15 CFR 740.1", per_page=1)
    assert len(articles) == 1
    art = articles[0]
    assert art["id"] == "740.1"
    assert art["title"]
    assert art["text"] == "Hello world."


def test_get_article_text(recorder):
    client = FederalRegisterClient()
    with recorder.use_cassette("federalregister_get_article_text.yaml"):
        text = client.get_article_text("740.1")
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
    budget.reset("ecfr")
    client = FederalRegisterClient()
    monkeypatch.setattr(client.cache, "get", lambda *args, **kwargs: DummyResponse())
    client._get_json("url", {})
    with pytest.raises(budget.BudgetExceededError):
        client._get_json("url", {})
    budget.reset("ecfr")
