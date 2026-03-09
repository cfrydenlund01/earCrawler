from __future__ import annotations

"""Offline loader for authoritative eCFR snapshot files (Title 15)."""

from pathlib import Path
import json
from typing import List, Dict, Any

from earCrawler.rag.corpus_contract import (
    SCHEMA_VERSION,
    normalize_ear_doc_id,
    normalize_ear_section_id,
    require_valid_corpus,
)
from earCrawler.rag.temporal import infer_snapshot_date, normalize_iso_date

CorpusDocument = Dict[str, Any]


def _coerce_str(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def load_ecfr_snapshot(path: Path) -> List[CorpusDocument]:
    """Load an approved offline eCFR snapshot into contract-shaped section docs.

    Snapshot format (JSONL, one object per line):
      { "section_id": "...", "heading": "...", "text": "...", "source_ref": "...", "url": "..." }

    Returns fully-populated section-level documents (chunk_kind='section') with
    canonical identifiers. Validation errors are aggregated via require_valid_corpus.
    """

    snapshot_path = Path(path)
    if not snapshot_path.exists():
        raise ValueError(f"Snapshot not found: {snapshot_path}")

    docs: List[CorpusDocument] = []
    with snapshot_path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except Exception as exc:  # pragma: no cover - guarded by tests
                raise ValueError(f"{snapshot_path}:{lineno} invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    f"{snapshot_path}:{lineno} expected object, got {type(payload).__name__}"
                )

            raw_section = payload.get("section_id")
            norm_section = normalize_ear_section_id(raw_section)
            section_value = norm_section or _coerce_str(raw_section).strip()
            raw_doc_id = payload.get("doc_id")
            norm_doc_id = normalize_ear_doc_id(raw_doc_id) if raw_doc_id else None
            raw_text = _coerce_str(payload.get("text"))
            doc: CorpusDocument = {
                "schema_version": SCHEMA_VERSION,
                "doc_id": norm_doc_id or section_value,
                "section_id": section_value,
                "text": raw_text,
                "chunk_kind": "section",
                "source": "ecfr_snapshot",
                "source_ref": _coerce_str(payload.get("source_ref")).strip(),
            }
            heading = _coerce_str(payload.get("heading")).strip()
            if heading:
                doc["title"] = heading
            url = _coerce_str(payload.get("url")).strip()
            if url:
                doc["url"] = url
            effective_date = normalize_iso_date(payload.get("effective_date"))
            if effective_date:
                doc["effective_date"] = effective_date
            effective_from = normalize_iso_date(payload.get("effective_from"))
            if effective_from:
                doc["effective_from"] = effective_from
            effective_to = normalize_iso_date(payload.get("effective_to"))
            if effective_to:
                doc["effective_to"] = effective_to
            snapshot_date = infer_snapshot_date(
                snapshot_date=payload.get("snapshot_date"),
                source_ref=payload.get("source_ref"),
                snapshot_id=payload.get("snapshot_id"),
            )
            if snapshot_date:
                doc["snapshot_date"] = snapshot_date
            docs.append(doc)

    if not docs:
        raise ValueError(f"No records found in snapshot: {snapshot_path}")

    # Canonicalize ids when possible (to keep deterministic ordering) before validation.
    for doc in docs:
        norm = normalize_ear_section_id(doc.get("section_id"))
        if norm:
            doc["section_id"] = norm
            if not doc.get("doc_id"):
                doc["doc_id"] = norm

    docs = sorted(docs, key=lambda d: str(d.get("doc_id") or ""))
    require_valid_corpus(docs)
    return docs


__all__ = ["load_ecfr_snapshot", "CorpusDocument"]
