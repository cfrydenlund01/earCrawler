from __future__ import annotations

import logging
from typing import Dict, Iterable

import pytest

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

from earCrawler.core.crawler import Crawler, TradeGovError, FederalRegisterError


class StubTradeGovClient:
    def __init__(self, entities: Iterable[Dict], fail: bool = False) -> None:
        self._entities = list(entities)
        self.fail = fail
        self.queries: list[str] = []

    def search_entities(self, query: str):
        self.queries.append(query)
        if self.fail:
            raise TradeGovError("boom")
        for ent in self._entities:
            yield ent


class StubFederalRegisterClient:
    def __init__(
        self, docs: dict[str, list[Dict]], fail_ids: Iterable[str] | None = None
    ) -> None:
        self.docs = docs
        self.fail_ids = set(fail_ids or [])
        self.queries: list[str] = []

    def search_documents(self, entity_id: str):
        self.queries.append(entity_id)
        if entity_id in self.fail_ids:
            raise FederalRegisterError("bad id")
        for doc in self.docs.get(entity_id, []):
            yield doc


def test_run_success():
    tg = StubTradeGovClient([{"id": "1"}, {"id": "2"}])
    fr = StubFederalRegisterClient({"1": [{"d": 1}], "2": [{"d": 2}]})
    crawler = Crawler(tg, fr)
    entities, documents = crawler.run("foo")
    assert entities == [{"id": "1"}, {"id": "2"}]
    assert documents == [{"d": 1}, {"d": 2}]
    assert tg.queries == ["foo"]
    assert fr.queries == ["1", "2"]


def test_empty_entities():
    tg = StubTradeGovClient([])
    fr = StubFederalRegisterClient({})
    crawler = Crawler(tg, fr)
    entities, documents = crawler.run("foo")
    assert entities == []
    assert documents == []


def test_tradegov_error_logged(caplog: pytest.LogCaptureFixture):
    tg = StubTradeGovClient([], fail=True)
    fr = StubFederalRegisterClient({})
    crawler = Crawler(tg, fr)
    with caplog.at_level(logging.WARNING):
        entities, documents = crawler.run("foo")
    assert entities == []
    assert documents == []
    assert any("Trade.gov" in rec.message for rec in caplog.records)


def test_federalregister_error_logged(caplog: pytest.LogCaptureFixture):
    tg = StubTradeGovClient([{"id": "good"}, {"id": "bad"}, {"id": "ok"}])
    fr = StubFederalRegisterClient(
        {"good": [{"d": 1}], "ok": [{"d": 2}]}, fail_ids=["bad"]
    )
    crawler = Crawler(tg, fr)
    with caplog.at_level(logging.WARNING):
        entities, documents = crawler.run("foo")
    assert entities == [{"id": "good"}, {"id": "bad"}, {"id": "ok"}]
    assert documents == [{"d": 1}, {"d": 2}]
    assert any("bad" in rec.message for rec in caplog.records)
