from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.rag.pipeline import _normalize_section_id

_SECTION_TERM_RE = re.compile(r"^\d{3}\.\S+$")
_SECTION_MENTION_RE = re.compile(
    r"\b(?:EAR-)?\d{3}\.\d+(?:\([a-z0-9]+\))*\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EnsureSectionsResult:
    requested_sections: list[str]
    normalized_sections: list[str]
    missing_before: list[str]
    fetched_records: int
    added_to_index: int


def extract_section_mentions(text: str) -> list[str]:
    """Extract normalized EAR section IDs mentioned in free text."""

    found: set[str] = set()
    for match in _SECTION_MENTION_RE.findall(str(text or "")):
        norm = _normalize_section_id(match)
        if norm:
            found.add(norm)
    return sorted(found)


def _terms_for_section(section: str) -> list[str]:
    section = str(section or "").strip()
    if not section:
        return []
    if _SECTION_TERM_RE.match(section):
        return [f"15 CFR {section}", section]
    return [section]


def _strip_ear_prefix(section_id: str) -> str:
    section_id = str(section_id or "").strip()
    if section_id.upper().startswith("EAR-"):
        return section_id[4:]
    return section_id


def _ecfr_source_url(section: str) -> str:
    part = (str(section).split(".", 1)[0] or "").strip()
    if part.isdigit():
        return f"https://www.ecfr.gov/current/title-15/part-{part}/section-{section}"
    return "https://www.ecfr.gov/current/title-15"


def _iter_jsonl(path: Path) -> Iterable[Mapping[str, object]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError:
                continue


def _existing_section_doc_pairs(corpus_path: Path) -> set[tuple[str, str]]:
    existing: set[tuple[str, str]] = set()
    for record in _iter_jsonl(corpus_path):
        section_value = (
            record.get("section")
            or record.get("span_id")
            or record.get("id")
            or record.get("entity_id")
        )
        norm = _normalize_section_id(section_value)
        if not norm:
            continue
        doc_id = str(record.get("doc_id") or "").strip()
        if doc_id:
            existing.add((norm, doc_id))
    return existing


def _existing_sections(corpus_path: Path) -> set[str]:
    existing: set[str] = set()
    for record in _iter_jsonl(corpus_path):
        section_value = (
            record.get("section")
            or record.get("span_id")
            or record.get("id")
            or record.get("entity_id")
        )
        norm = _normalize_section_id(section_value)
        if norm:
            existing.add(norm)
    return existing


def _append_jsonl(path: Path, records: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_indexed_ids(index_path: Path) -> set[str]:
    meta_path = index_path.with_suffix(".pkl")
    if not meta_path.exists():
        return set()
    try:
        with meta_path.open("rb") as handle:
            metadata = pickle.load(handle)
    except Exception:
        return set()
    ids: set[str] = set()
    if isinstance(metadata, list):
        for rec in metadata:
            if isinstance(rec, dict) and rec.get("id"):
                ids.add(str(rec["id"]))
    return ids


def ensure_ecfr_sections(
    sections: Iterable[str],
    *,
    corpus_path: Path = Path("data") / "ecfr_sections.jsonl",
    index_path: Path = Path("data") / "faiss" / "ecfr.index.faiss",
    model_name: str = "all-MiniLM-L12-v2",
    per_page: int = 2,
    refresh: bool = False,
    update_index: bool = True,
    client: FederalRegisterClient | None = None,
) -> EnsureSectionsResult:
    """Ensure requested EAR section IDs exist in the eCFR-backed corpus and FAISS index."""

    requested = [str(s).strip() for s in sections if str(s).strip()]
    normalized: list[str] = []
    for sec in requested:
        norm = _normalize_section_id(sec)
        if norm:
            normalized.append(norm)
    normalized = sorted(set(normalized))

    existing_sections_before = _existing_sections(corpus_path)
    missing_before = sorted(set(normalized) - existing_sections_before)

    fr_client = client or FederalRegisterClient()
    fetched_records: list[Mapping[str, object]] = []

    for norm_sec in normalized:
        if not refresh and norm_sec in existing_sections_before:
            continue
        raw_sec = _strip_ear_prefix(norm_sec)
        text = fr_client.get_section_text(raw_sec)
        if not text:
            # Fallback to a search-style retrieval when direct section fetch fails.
            docs: list[dict] = []
            for term in _terms_for_section(raw_sec):
                docs = fr_client.get_ear_articles(term, per_page=max(1, int(per_page)))
                if docs:
                    break
            for doc in docs:
                candidate = str(doc.get("text") or "").strip()
                if candidate:
                    text = candidate
                    break
        if not text:
            continue
        fetched_records.append(
            {
                "id": norm_sec,
                "doc_id": raw_sec,
                "section": raw_sec,
                "span_id": raw_sec,
                "title": f"15 CFR {raw_sec}",
                "text": text,
                "source_url": _ecfr_source_url(raw_sec),
                "provider": "ecfr.gov",
            }
        )

    if fetched_records:
        _append_jsonl(corpus_path, fetched_records)

    added_to_index = 0
    if update_index and fetched_records:
        try:
            from earCrawler.rag.retriever import Retriever
            from api_clients.tradegov_client import TradeGovClient
        except Exception as exc:  # pragma: no cover - optional deps missing
            raise RuntimeError(f"RAG index update unavailable: {exc}") from exc

        indexed_ids = _load_indexed_ids(index_path)
        to_add: list[dict] = []
        for rec in fetched_records:
            rec_id = str(rec.get("id") or "")
            if not rec_id or rec_id in indexed_ids:
                continue
            to_add.append(
                {
                    "id": rec_id,
                    "section": rec.get("section"),
                    "span_id": rec.get("span_id"),
                    "text": rec.get("text"),
                    "source_url": rec.get("source_url"),
                    "provider": rec.get("provider"),
                    "title": rec.get("title"),
                }
            )
        if to_add:
            retriever = Retriever(
                TradeGovClient(),
                FederalRegisterClient(),
                model_name=model_name,
                index_path=index_path,
            )
            retriever.add_documents(to_add)
            added_to_index = len(to_add)

    return EnsureSectionsResult(
        requested_sections=requested,
        normalized_sections=normalized,
        missing_before=missing_before,
        fetched_records=len(fetched_records),
        added_to_index=added_to_index,
    )


def ensure_fr_sections(*args, **kwargs) -> EnsureSectionsResult:
    """Backwards-compatible alias; prefer ensure_ecfr_sections()."""

    return ensure_ecfr_sections(*args, **kwargs)
