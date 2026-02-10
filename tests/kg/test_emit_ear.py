from __future__ import annotations

import json
from pathlib import Path

from earCrawler.kg.emit_ear import emit_ear
from earCrawler.kg.iri import paragraph_iri


def _write_records(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def test_emit_ear_deterministic(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    records = [
        {
            "id": 1,
            "sha256": "a" * 64,
            "source_url": "http://example.com/a",
            "date": "2020-01-01",
        },
        {
            "id": 2,
            "sha256": "b" * 64,
            "source_url": "not a url",
            "date": "2020-01-02",
            "section": "734.3",
        },
    ]
    _write_records(data_dir / "ear_corpus.jsonl", records)

    out_dir = tmp_path / "out"
    path1, count1 = emit_ear(data_dir, out_dir)
    assert path1.exists()
    content1 = path1.read_bytes()
    path2, count2 = emit_ear(data_dir, out_dir)
    content2 = path2.read_bytes()
    assert content1 == content2
    text = content1.decode("utf-8")
    assert f"<{paragraph_iri('a' * 64)}>" in text
    assert "dct:source" in text
    assert "dct:issued" in text
