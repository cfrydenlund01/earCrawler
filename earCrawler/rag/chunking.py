from __future__ import annotations

"""Deterministic chunking for EAR section text."""

from typing import List, Literal, Dict, Any
import re

from earCrawler.rag.corpus_contract import normalize_ear_section_id

CorpusDocument = Dict[str, Any]

_LETTER_MARKER_RE = re.compile(r"(?m)^\s*\(\s*([a-z])\s*\)\s")
_DIGIT_MARKER_RE = re.compile(r"(?m)^\s*\(\s*(\d+)\s*\)\s")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_NEWLINE_SPLIT_RE = re.compile(r"\n+")


def _split_by_whitespace(text: str, *, max_chars: int) -> list[str]:
    """Deterministically split a long block into <=max_chars segments on whitespace.

    Used as a fallback when upstream text contains long unbroken paragraphs.
    """

    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def _flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append(" ".join(current))
            current = []
            current_len = 0

    for word in words:
        if not current:
            if len(word) <= max_chars:
                current = [word]
                current_len = len(word)
                continue
            # Extremely long "word" fallback: hard-slice deterministically.
            start = 0
            while start < len(word):
                chunks.append(word[start : start + max_chars])
                start += max_chars
            continue

        needed = 1 + len(word)
        if current_len + needed <= max_chars:
            current.append(word)
            current_len += needed
            continue

        _flush()
        if len(word) <= max_chars:
            current = [word]
            current_len = len(word)
            continue
        start = 0
        while start < len(word):
            chunks.append(word[start : start + max_chars])
            start += max_chars

    _flush()
    return chunks


def _paragraph_chunks(container: CorpusDocument, max_chars: int) -> List[CorpusDocument]:
    """Split an oversized chunk into paragraph children (blank-line delimited).

    Keeps a shortened container (still <= max_chars) to preserve parent_id targets.
    Raises if paragraphs cannot satisfy max_chars.
    """

    text = str(container.get("text") or "").strip()
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
    if len(paragraphs) <= 1:
        # Some upstream sources don't preserve blank lines; fall back to single-newline
        # or whitespace splitting to keep builds robust and deterministic.
        paragraphs = [p.strip() for p in _NEWLINE_SPLIT_RE.split(text) if p.strip()]
        if len(paragraphs) <= 1:
            paragraphs = _split_by_whitespace(text, max_chars=max_chars)
        if len(paragraphs) <= 1:
            raise ValueError(
                f"Chunk for {container.get('doc_id')} exceeds max_chars={max_chars} and cannot be split deterministically."
            )

    # Enforce size constraints after selecting a split strategy.
    for para in paragraphs:
        if len(para) > max_chars:
            # whitespace splitter should prevent this, but keep defensive.
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

    letter_matches = list(_LETTER_MARKER_RE.finditer(raw_text))
    chunks: List[CorpusDocument] = []

    if not letter_matches:
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

    # Always emit a base section container so child chunks have a valid parent_id.
    section_doc = {
        "doc_id": norm_section,
        "section_id": norm_section,
        "text": raw_text.strip(),
        "chunk_kind": "section",
        "ordinal": 0,
    }
    if heading_val:
        section_doc["title"] = heading_val
    chunks.extend(_emit_chunk(section_doc, max_chars))

    filtered_matches = []
    for match in letter_matches:
        letter = match.group(1).lower()
        # Avoid treating common roman numeral markers as top-level subsection labels.
        if letter in {"i", "v", "x"}:
            continue
        filtered_matches.append(match)

    if filtered_matches:
        labels = [m.group(1).lower() for m in filtered_matches]
        # If top-level labels repeat within a section, they are almost certainly
        # from nested enumerations or formatting artifacts. In that case, skip
        # subsection splitting and rely on the base section chunk.
        if len(set(labels)) != len(labels):
            filtered_matches = []

    for idx, match in enumerate(filtered_matches):
        letter = match.group(1).lower()
        start = match.start()
        end = (
            filtered_matches[idx + 1].start()
            if idx + 1 < len(filtered_matches)
            else len(raw_text)
        )
        letter_block = raw_text[start:end].strip()
        letter_id = f"{norm_section}({letter})"

        digit_matches = list(_DIGIT_MARKER_RE.finditer(letter_block))
        if digit_matches:
            digit_labels = [m.group(1) for m in digit_matches]
            # If numeric markers repeat within a subsection, they are almost certainly nested
            # under deeper enumerations (A)/(i)/... and cannot be represented uniquely at the
            # (letter)(number) level. In that case, keep the full letter block as a single chunk.
            if len(set(digit_labels)) != len(digit_labels):
                digit_matches = []

        if not digit_matches:
            subsection_doc: CorpusDocument = {
                "doc_id": letter_id,
                "section_id": letter_id,
                "text": letter_block,
                "chunk_kind": "subsection",
                "parent_id": norm_section,
                "ordinal": idx + 1,
            }
            if heading_val:
                subsection_doc["title"] = heading_val
            chunks.extend(_emit_chunk(subsection_doc, max_chars))
            continue

        # Emit the letter container for any lead-in text before the first numeric marker.
        letter_lead = letter_block[: digit_matches[0].start()].strip()
        if letter_lead:
            subsection_doc = {
                "doc_id": letter_id,
                "section_id": letter_id,
                "text": letter_lead,
                "chunk_kind": "subsection",
                "parent_id": norm_section,
                "ordinal": idx + 1,
            }
            if heading_val:
                subsection_doc["title"] = heading_val
            chunks.extend(_emit_chunk(subsection_doc, max_chars))

        for jdx, dmatch in enumerate(digit_matches):
            num = dmatch.group(1)
            dstart = dmatch.start()
            dend = digit_matches[jdx + 1].start() if jdx + 1 < len(digit_matches) else len(letter_block)
            digit_block = letter_block[dstart:dend].strip()
            digit_id = f"{letter_id}({num})"
            digit_doc: CorpusDocument = {
                "doc_id": digit_id,
                "section_id": digit_id,
                "text": digit_block,
                "chunk_kind": "subsection",
                "parent_id": letter_id,
                "ordinal": jdx + 1,
            }
            if heading_val:
                digit_doc["title"] = heading_val
            chunks.extend(_emit_chunk(digit_doc, max_chars))

    return chunks


__all__ = ["chunk_section_text", "CorpusDocument"]
