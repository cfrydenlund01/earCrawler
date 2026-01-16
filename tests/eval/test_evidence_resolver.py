from __future__ import annotations

import json
from pathlib import Path

from earCrawler.eval.evidence_resolver import load_corpus_index, resolve_dataset


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_resolve_dataset_matches_corpus(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    _write_jsonl(
        corpus_path,
        [
            {
                "id": "EAR-740.1",
                "section": "740.1",
                "text": "License Exceptions intro",
                "source_url": "http://example/740",
            },
            {
                "id": "EAR-742.4(a)(1)",
                "section": "742.4(a)(1)",
                "text": "A license is required.",
                "source_url": "http://example/742",
            },
        ],
    )
    items = [
        {
            "id": "item-1",
            "ear_sections": ["740.1"],
            "evidence": {"doc_spans": [{"doc_id": "EAR-740", "span_id": "740.1"}]},
        }
    ]
    index = load_corpus_index(corpus_path)
    report = resolve_dataset("ds", items, index)
    assert report["missing_sections"] == []
    assert report["missing_spans"] == []
    resolved = report["items"][0]["resolved_sections"]
    assert resolved and resolved[0]["records"][0]["text_preview"].startswith("License")


def test_resolve_dataset_flags_missing_sections_and_spans(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    _write_jsonl(
        corpus_path,
        [
            {
                "id": "EAR-744.6(b)(3)",
                "section": "744.6(b)(3)",
                "text": "U.S. persons controls.",
            },
        ],
    )
    items = [
        {
            "id": "item-2",
            "ear_sections": ["740.9(a)(2)"],
            "evidence": {"doc_spans": [{"doc_id": "EAR-740", "span_id": "740.5"}]},
        }
    ]
    index = load_corpus_index(corpus_path)
    report = resolve_dataset("ds", items, index)
    assert "740.9(a)(2)" in report["missing_sections"]
    # span_id is not in corpus and does not align to the ear_sections entry
    assert "EAR-740.5" in report["missing_spans"]
