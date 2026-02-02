from __future__ import annotations

"""Build retrieval corpus from an authoritative eCFR snapshot."""

import hashlib
from pathlib import Path
from typing import Iterable, List, Dict, Any

from earCrawler.rag.corpus_contract import (
    SCHEMA_VERSION,
    require_valid_corpus,
)
from earCrawler.rag.ecfr_snapshot_loader import load_ecfr_snapshot, CorpusDocument
from earCrawler.rag.chunking import chunk_section_text
from earCrawler.utils.log_json import JsonLogger

_logger = JsonLogger("rag-corpus")


def compute_corpus_digest(docs: Iterable[Dict[str, Any]]) -> str:
    """Deterministic sha256 over (doc_id + text) in doc_id order."""

    ordered = sorted(docs, key=lambda d: str(d.get("doc_id") or ""))
    digest = hashlib.sha256()
    for doc in ordered:
        doc_id = str(doc.get("doc_id") or "")
        text = str(doc.get("text") or "")
        digest.update(doc_id.encode("utf-8"))
        digest.update(b"\n")
        digest.update(text.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_retrieval_corpus(
    snapshot_path: Path,
    *,
    source_ref: str | None = None,
    chunk_max_chars: int = 6000,
) -> List[CorpusDocument]:
    """Load snapshot, chunk deterministically, and validate corpus documents."""

    sections = load_ecfr_snapshot(snapshot_path)
    if chunk_max_chars <= 0:
        raise ValueError("chunk_max_chars must be positive")

    docs: List[CorpusDocument] = []
    for section in sections:
        resolved_source_ref = source_ref or section.get("source_ref") or ""
        if not resolved_source_ref:
            raise ValueError(
                f"source_ref missing for section {section.get('section_id')}; "
                "provide --source-ref or include it in the snapshot."
            )
        heading = section.get("title") or section.get("heading")
        url = section.get("url")
        chunks = chunk_section_text(
            section["section_id"],
            heading,
            section.get("text") or "",
            max_chars=chunk_max_chars,
            strategy="section_subsection",
        )
        for chunk in chunks:
            doc: CorpusDocument = {
                **chunk,
                "schema_version": SCHEMA_VERSION,
                "source": section.get("source") or "ecfr_snapshot",
                "source_ref": resolved_source_ref,
            }
            if heading and "title" not in doc:
                doc["title"] = heading
            if url and "url" not in doc:
                doc["url"] = url
            docs.append(doc)

    docs = sorted(docs, key=lambda d: str(d.get("doc_id") or ""))
    require_valid_corpus(docs)
    digest = compute_corpus_digest(docs)
    unique_sections = len({d.get("section_id") for d in docs})
    _logger.info(
        "rag.corpus.build",
        details={
            "doc_count": len(docs),
            "unique_sections": unique_sections,
            "source_ref": source_ref or sections[0].get("source_ref"),
            "digest": digest,
        },
    )
    return docs


def write_corpus_jsonl(path: Path, docs: Iterable[Dict[str, Any]]) -> Path:
    """Write corpus docs to JSONL in deterministic order."""

    ordered = sorted(docs, key=lambda d: str(d.get("doc_id") or ""))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for doc in ordered:
            import json

            handle.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n")
    return target


__all__ = ["build_retrieval_corpus", "compute_corpus_digest", "write_corpus_jsonl"]
