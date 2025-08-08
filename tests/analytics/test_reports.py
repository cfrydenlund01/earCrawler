from __future__ import annotations

from pathlib import Path
from typing import Dict, Set

import pytest

import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

from earCrawler.analytics import reports

FIXTURES = Path("tests/fixtures")


def test_load_corpus_yields_records() -> None:
    records = list(reports.load_corpus("ear", data_dir=FIXTURES))
    assert len(records) == 3
    assert records[0]["entities"]["PERSON"] == ["Alice"]


@pytest.fixture()
def use_fixture_corpus(monkeypatch):
    original = reports.load_corpus
    monkeypatch.setattr(
        reports,
        "load_corpus",
        lambda source, data_dir=Path("data"): original(source, FIXTURES),
    )


def test_top_entities(use_fixture_corpus) -> None:
    result = reports.top_entities("ear", "PERSON", n=2)
    assert result == [("Alice", 2), ("Bob", 1)]


def test_term_frequency(use_fixture_corpus) -> None:
    result = dict(reports.term_frequency("ear", n=5))
    assert result["openai"] == 3
    assert result["acme"] == 2


def test_cooccurrence(use_fixture_corpus) -> None:
    result: Dict[str, Set[str]] = reports.cooccurrence("ear", "PERSON")
    assert result == {"Alice": {"Bob"}, "Bob": {"Alice"}}
