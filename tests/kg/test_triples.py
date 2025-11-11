import json
from pathlib import Path

from earCrawler.kg.triples import export_triples


def test_export_triples_creates_file(tmp_path, monkeypatch):
    # prepare a minimal JSONL fixture
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rec = {"identifier": "123_0", "text": "Hello world", "entities": {"orgs": ["OrgX"]}}
    (data_dir / "ear_corpus.jsonl").write_text(json.dumps(rec) + "\n")
    (data_dir / "nsf_corpus.jsonl").write_text(json.dumps(rec) + "\n")
    out_ttl = tmp_path / "kg.ttl"
    export_triples(data_dir, out_ttl)
    content = out_ttl.read_text()
    assert "ex:paragraph_123_0 rdf:type ex:Paragraph" in content
    assert "ex:entity_orgx rdf:type ex:Entity" in content
