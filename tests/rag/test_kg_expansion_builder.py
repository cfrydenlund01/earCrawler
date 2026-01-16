from __future__ import annotations

import json
from pathlib import Path

from earCrawler.rag.kg_expansion_builder import build_expansion_mapping


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_build_expansion_mapping_uses_manifest_refs(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    _write_jsonl(
        corpus_path,
        [
            {
                "id": "EAR-740.1",
                "section": "740.1",
                "text": "License exceptions overview",
                "source_url": "http://example/740",
            },
            {
                "id": "EAR-740.9(a)(2)",
                "section": "740.9(a)(2)",
                "text": "Temporary exports allowed.",
                "source_url": "http://example/7409",
            },
        ],
    )
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "ear_sections": ["EAR-740.1"],
                "evidence": {
                    "kg_nodes": ["node-ds"],
                    "kg_paths": ["path-ds"],
                    "doc_spans": [{"doc_id": "EAR-740", "span_id": "740.1"}],
                },
            }
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "datasets": [{"id": "ds1", "file": str(dataset_path)}],
                "references": {
                    "sections": {"EAR-740": ["740.1", "740.9(a)(2)"]},
                    "kg_nodes": ["node-ref"],
                    "kg_paths": ["path-ref"],
                },
            }
        ),
        encoding="utf-8",
    )

    mapping = build_expansion_mapping(corpus_path, manifest_path)
    assert "EAR-740.1" in mapping
    entry = mapping["EAR-740.1"]
    assert entry["text"].startswith("License exceptions overview")
    assert "EAR-740.9(a)(2)" in entry["related_sections"]
    assert "node-ref" in entry["label_hints"]
    assert "node-ds" in entry["label_hints"]
