from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.kg.loader import enrich_entities_with_tradegov
from earCrawler.kg.emit_ear import fetch_ear_corpus, emit_ear
from earCrawler.kg.triples import emit_tradegov_entities


def test_ingest_contract(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("TRADEGOV_API_KEY", "DUMMY")
    tg = TradeGovClient()
    fr = FederalRegisterClient()

    with recorder.use_cassette("tradegov_lookup_entity.yaml"):
        enriched = enrich_entities_with_tradegov([{"name": "ACME Corp"}], tg)
    ent_ttl, ent_count = emit_tradegov_entities(enriched, tmp_path / "kg")
    assert ent_count >= 3
    ttl_text = ent_ttl.read_text(encoding="utf-8")
    assert "Acme Corp" in ttl_text

    with recorder.use_cassette("federalregister_get_ear_articles.yaml"):
        fetch_ear_corpus("export", fr, out_dir=tmp_path / "ear")
    ear_ttl, ear_count = emit_ear(tmp_path / "ear", tmp_path / "kg")
    assert ear_count >= 1
    assert "2023-12345" in ear_ttl.read_text(encoding="utf-8")
