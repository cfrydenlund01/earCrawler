from __future__ import annotations

import json
from pathlib import Path

from earCrawler.kg.emit_nsf import emit_nsf


def _write_records(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def test_emit_nsf_deterministic(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    records = [
        {
            "id": "n1",
            "sha256": "c" * 64,
            "source_url": "http://example.org/nsf",
            "date": "2021-02-03",
            "entities": ["Example Org"],
        }
    ]
    _write_records(data_dir / "nsf_corpus.jsonl", records)

    out_dir = tmp_path / "out"
    path1, count1 = emit_nsf(data_dir, out_dir)
    assert path1.exists()
    content1 = path1.read_bytes()
    path2, count2 = emit_nsf(data_dir, out_dir)
    content2 = path2.read_bytes()
    assert content1 == content2
    text = content1.decode("utf-8")
    assert "ear:p_" + "c" * 16 in text
    assert "prov:wasDerivedFrom" in text
