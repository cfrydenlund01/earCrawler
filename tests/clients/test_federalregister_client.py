from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api_clients.federalregister_client import FederalRegisterClient


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
