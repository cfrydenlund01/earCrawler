from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api_clients.tradegov_client import TradeGovClient


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
