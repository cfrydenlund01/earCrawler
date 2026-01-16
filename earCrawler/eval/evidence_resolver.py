from __future__ import annotations

"""Helpers for resolving evaluation evidence against the local corpus.

The resolver normalizes EAR section identifiers in the same way the RAG
pipeline does and asserts that every referenced section/span exists in the
loaded corpus. It emits a compact, deterministic report so CI can gate on
missing or mismatched evidence without dumping full Federal Register text.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from earCrawler.rag.pipeline import _normalize_section_id


TEXT_KEYS: tuple[str, ...] = (
    "text",
    "body",
    "content",
    "paragraph",
    "summary",
    "snippet",
    "title",
)


@dataclass(frozen=True)
class CorpusRecordPreview:
    record_id: str | None
    source_url: str | None
    text_preview: str
    text_length: int


def _short_text(record: Mapping[str, object], *, limit: int = 240) -> str:
    for key in TEXT_KEYS:
        val = record.get(key)
        if val:
            text = str(val).strip()
            return text[:limit]
    return ""


def load_corpus_index(path: Path) -> dict[str, list[Mapping[str, object]]]:
    """Load a JSONL corpus and index it by normalized section id."""

    index: dict[str, list[Mapping[str, object]]] = {}
    if not path.exists():
        raise FileNotFoundError(f"Corpus not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            section_value = (
                record.get("section")
                or record.get("span_id")
                or record.get("id")
                or record.get("entity_id")
            )
            normalized = _normalize_section_id(section_value)
            if not normalized:
                continue
            index.setdefault(normalized, []).append(record)
    for key in list(index.keys()):
        index[key] = sorted(
            index[key],
            key=lambda rec: str(
                rec.get("id") or rec.get("title") or rec.get("section") or ""
            ),
        )
    return index


def _preview(record: Mapping[str, object]) -> CorpusRecordPreview:
    preview = _short_text(record)
    text_raw = ""
    for key in TEXT_KEYS:
        if record.get(key):
            text_raw = str(record.get(key) or "")
            break
    return CorpusRecordPreview(
        record_id=str(record.get("id") or record.get("section") or ""),
        source_url=str(record.get("source_url") or record.get("source") or ""),
        text_preview=preview,
        text_length=len(text_raw),
    )


def resolve_item(
    item: Mapping[str, object],
    corpus_index: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    """Resolve a single eval item against the corpus index."""

    item_id = str(item.get("id") or "")
    sections_raw: Sequence[object] = item.get("ear_sections") or []
    normalized_sections = {
        _normalize_section_id(sec): str(sec)
        for sec in sections_raw
        if _normalize_section_id(sec)
    }

    resolved_sections = []
    missing_sections: set[str] = set()
    for norm_id, raw in normalized_sections.items():
        matches = corpus_index.get(norm_id, [])
        if not matches:
            missing_sections.add(raw)
        previews = [_preview(rec) for rec in matches]
        if previews:
            resolved_sections.append(
                {
                    "section_id": norm_id,
                    "records": [
                        {
                            "id": p.record_id,
                            "source_url": p.source_url,
                            "text_preview": p.text_preview,
                            "text_length": p.text_length,
                        }
                        for p in previews
                    ],
                }
            )

    evidence = item.get("evidence") or {}
    doc_spans: Sequence[Mapping[str, object]] = evidence.get("doc_spans") or []
    missing_spans: set[str] = set()
    span_mismatches: set[str] = set()
    for span in doc_spans:
        span_id_norm = _normalize_section_id(span.get("span_id"))
        if span_id_norm and span_id_norm not in normalized_sections:
            span_mismatches.add(span_id_norm)
        if span_id_norm and span_id_norm not in corpus_index:
            missing_spans.add(span_id_norm)

    return {
        "item_id": item_id,
        "ear_sections": list(normalized_sections.keys()),
        "resolved_sections": resolved_sections,
        "missing_sections": sorted(missing_sections),
        "missing_spans": sorted(missing_spans | span_mismatches),
    }


def resolve_dataset(
    dataset_id: str,
    items: Iterable[Mapping[str, object]],
    corpus_index: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    """Resolve all items in a dataset and summarize missing references."""

    item_results = [resolve_item(item, corpus_index) for item in items]
    missing_sections = {sec for res in item_results for sec in res["missing_sections"]}
    missing_spans = {span for res in item_results for span in res["missing_spans"]}
    return {
        "dataset_id": dataset_id,
        "items": item_results,
        "missing_sections": sorted(missing_sections),
        "missing_spans": sorted(missing_spans),
    }


__all__ = ["load_corpus_index", "resolve_dataset", "resolve_item"]
