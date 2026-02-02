from __future__ import annotations

"""
Rebuild a contract-conformant retrieval corpus from data/fr_sections.jsonl.

This is intentionally a thin, deterministic transformer:
- De-duplicates by canonical EAR section id.
- Emits retrieval-corpus.v1 fields required by validators and downstream consumers.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from earCrawler.rag.corpus_contract import (
    SCHEMA_VERSION,
    normalize_ear_section_id,
    require_valid_corpus,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            records.append(json.loads(stripped))
    return records


def _chunk_kind(section_id: str) -> str:
    return "subsection" if "(" in section_id else "section"


def build_retrieval_corpus(*, input_path: Path, output_path: Path) -> list[dict[str, Any]]:
    raw_records = _iter_jsonl(input_path)
    source_ref = f"{input_path.name}:sha256:{_file_sha256(input_path)}"

    grouped: dict[str, list[dict[str, Any]]] = {}
    for rec in raw_records:
        raw_id = rec.get("id") or rec.get("section") or rec.get("span_id")
        section_id = normalize_ear_section_id(raw_id)
        if not section_id:
            continue
        text = str(rec.get("text") or "").strip()
        if not text:
            continue
        grouped.setdefault(section_id, []).append(rec)

    docs: list[dict[str, Any]] = []
    for section_id in sorted(grouped.keys()):
        items = grouped[section_id]
        items_sorted = sorted(
            items,
            key=lambda r: (
                str(r.get("provider") or ""),
                str(r.get("source_url") or ""),
                str(r.get("title") or ""),
            ),
        )
        seen_text_hashes: set[str] = set()
        texts: list[str] = []
        for item in items_sorted:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            h = _sha256_bytes(text.encode("utf-8"))
            if h in seen_text_hashes:
                continue
            seen_text_hashes.add(h)
            texts.append(text)

        merged = "\n\n".join(texts).strip()
        if not merged:
            continue

        doc: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "doc_id": section_id,
            "section_id": section_id,
            "text": merged,
            "chunk_kind": _chunk_kind(section_id),
            "source": "other",
            "source_ref": source_ref,
            "hash": _sha256_bytes(merged.encode("utf-8")),
        }

        # Backwards-compat for older consumers that still look for these keys.
        doc["id"] = doc["doc_id"]
        doc["section"] = section_id.removeprefix("EAR-")

        docs.append(doc)

    require_valid_corpus(docs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for doc in docs:
            handle.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n")
    return docs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data") / "fr_sections.jsonl",
        help="Input JSONL file (default: data/fr_sections.jsonl).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data") / "retrieval_corpus.jsonl",
        help="Output JSONL file (default: data/retrieval_corpus.jsonl).",
    )
    args = parser.parse_args()
    docs = build_retrieval_corpus(input_path=args.input, output_path=args.out)
    print(f"Wrote {len(docs)} documents -> {args.out}")


if __name__ == "__main__":
    main()

