from __future__ import annotations

import json
from pathlib import Path

from earCrawler.corpus.identity import build_record_id
from earCrawler.kg.emit_nsf import emit_nsf
from earCrawler.kg.iri import paragraph_iri


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
    assert f"<{paragraph_iri('c' * 64)}>" in text
    assert "prov:wasDerivedFrom" in text


def test_emit_nsf_keeps_distinct_paragraph_nodes_for_duplicate_text(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shared_hash = "e" * 64
    records = [
        {
            "source": "nsf",
            "id": build_record_id("nsf", "NSF-001:0"),
            "record_id": build_record_id("nsf", "NSF-001:0"),
            "identifier": "NSF-001:0",
            "content_sha256": shared_hash,
            "sha256": shared_hash,
            "source_url": "http://example.org/nsf/1",
            "date": "2021-02-03",
            "entities": ["Example Org"],
        },
        {
            "source": "nsf",
            "id": build_record_id("nsf", "NSF-002:0"),
            "record_id": build_record_id("nsf", "NSF-002:0"),
            "identifier": "NSF-002:0",
            "content_sha256": shared_hash,
            "sha256": shared_hash,
            "source_url": "http://example.org/nsf/2",
            "date": "2021-02-04",
            "entities": ["Example Org"],
        },
    ]
    _write_records(data_dir / "nsf_corpus.jsonl", records)

    out_dir = tmp_path / "out"
    path, _ = emit_nsf(data_dir, out_dir)
    text = path.read_text(encoding="utf-8")

    first_iri = paragraph_iri(build_record_id("nsf", "NSF-001:0"))
    second_iri = paragraph_iri(build_record_id("nsf", "NSF-002:0"))
    assert f"<{first_iri}>" in text
    assert f"<{second_iri}>" in text
    assert first_iri != second_iri
