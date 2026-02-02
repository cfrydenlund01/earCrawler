from __future__ import annotations

"""Deterministic chunking for EAR section text."""

from typing import List, Literal, Dict, Any
import re

from earCrawler.rag.corpus_contract import normalize_ear_section_id

CorpusDocument = Dict[str, Any]

_SUBSECTION_RE = re.compile(r"(?m)^\s*\(([a-z0-9]+)\)\s")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")


def _paragraph_chunks(container: CorpusDocument, max_chars: int) -> List[CorpusDocument]:
    """Split an oversized chunk into paragraph children (blank-line delimited).

    Keeps a shortened container (still <= max_chars) to preserve parent_id targets.
    Raises if paragraphs cannot satisfy max_chars.
    """

    text = str(container.get("text") or "").strip()
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
    if len(paragraphs) <= 1:
        raise ValueError(
            f"Chunk for {container.get('doc_id')} exceeds max_chars={max_chars} and cannot be split on paragraph boundaries."
        )
    for para in paragraphs:
        if len(para) > max_chars:
            raise ValueError(
                f"Paragraph for {container.get('doc_id')} exceeds max_chars={max_chars} (len={len(para)})."
            )

    kept: list[str] = []
    remaining = max_chars
    for para in paragraphs:
        needed = len(para) + (2 if kept else 0)
        if needed <= remaining:
            kept.append(para)
            remaining -= needed
        else:
            break
    if not kept:
        kept.append(paragraphs[0])
    container_copy = dict(container)
    container_copy["text"] = "\n\n".join(kept)
    results: List[CorpusDocument] = [container_copy]

    title = container.get("title")
    base_id = str(container.get("doc_id") or "").strip()
    base_section = str(container.get("section_id") or "").strip() or base_id
    for idx, para in enumerate(paragraphs, start=1):
        para_doc: CorpusDocument = {
            "doc_id": f"{base_id}#p{idx:04d}",
            "section_id": base_id,
            "text": para,
            "chunk_kind": "paragraph",
            "parent_id": base_id,
            "ordinal": idx,
        }
        if title:
            para_doc["title"] = title
        results.append(para_doc)
    return results


def _emit_chunk(doc: CorpusDocument, max_chars: int) -> List[CorpusDocument]:
    """Return chunk(s) for a container, enforcing max_chars deterministically."""

    text = str(doc.get("text") or "").strip()
    container = dict(doc)
    container["text"] = text
    if len(text) <= max_chars:
        return [container]
    return _paragraph_chunks(container, max_chars)


def chunk_section_text(
    section_id: str,
    heading: str | None,
    text: str,
    *,
    max_chars: int,
    strategy: Literal["section_subsection"] = "section_subsection",
) -> List[CorpusDocument]:
    """Deterministically split section text into contract-ready chunks.

    Rules (section_subsection strategy):
    - Detect subsection markers `(a)`, `(b)`, ... at line starts.
    - When subsections exist:
        * Emit base section chunk only when lead-in text appears before the first marker.
        * Emit one chunk per subsection in source order.
    - When no markers exist: emit a single section chunk.
    - Chunks exceeding `max_chars` are split on paragraph boundaries (blank lines) with
      stable suffixes `#p0001`, `#p0002`, ... and `chunk_kind='paragraph'`.
    """

    if strategy != "section_subsection":
        raise ValueError(f"Unsupported chunking strategy: {strategy}")

    norm_section = normalize_ear_section_id(section_id)
    if not norm_section:
        raise ValueError(f"Invalid section_id: {section_id}")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Empty text for section {norm_section}")

    heading_val = (heading or "").strip()
    raw_text = text

    matches = list(_SUBSECTION_RE.finditer(raw_text))
    chunks: List[CorpusDocument] = []

    if not matches:
        section_doc: CorpusDocument = {
            "doc_id": norm_section,
            "section_id": norm_section,
            "text": raw_text.strip(),
            "chunk_kind": "section",
            "ordinal": 0,
        }
        if heading_val:
            section_doc["title"] = heading_val
        return _emit_chunk(section_doc, max_chars)

    lead_text = raw_text[: matches[0].start()].strip()
    if lead_text:
        section_doc = {
            "doc_id": norm_section,
            "section_id": norm_section,
            "text": lead_text,
            "chunk_kind": "section",
            "ordinal": 0,
        }
        if heading_val:
            section_doc["title"] = heading_val
        chunks.extend(_emit_chunk(section_doc, max_chars))

    for idx, match in enumerate(matches):
        label = match.group(1).lower()
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_text)
        subsection_text = raw_text[start:end].strip()
        subsection_id = f"{norm_section}({label})"
        subsection_doc: CorpusDocument = {
            "doc_id": subsection_id,
            "section_id": subsection_id,
            "text": subsection_text,
            "chunk_kind": "subsection",
            "parent_id": norm_section,
            "ordinal": idx + 1,
        }
        if heading_val:
            subsection_doc["title"] = heading_val
        chunks.extend(_emit_chunk(subsection_doc, max_chars))

    return chunks


__all__ = ["chunk_section_text", "CorpusDocument"]
