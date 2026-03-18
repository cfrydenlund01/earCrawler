from __future__ import annotations

"""Artifact sanitizers used by eval_rag_llm reporting outputs."""

from typing import Iterable, Mapping

from earCrawler.rag.pipeline import _normalize_section_id


def sanitize_citations(citations: Iterable[Mapping[str, object]] | None) -> list[dict]:
    cleaned: list[dict] = []
    for cit in citations or []:
        if not isinstance(cit, Mapping):
            continue
        cleaned.append(
            {
                "section_id": cit.get("section_id"),
                "quote": cit.get("quote"),
                "span_id": cit.get("span_id"),
                "source": cit.get("source"),
            }
        )
    return cleaned


def sanitize_retrieved_docs(docs: Iterable[Mapping[str, object]] | None) -> list[dict]:
    cleaned: list[dict] = []
    for doc in docs or []:
        if not isinstance(doc, Mapping):
            continue
        cleaned.append(
            {
                "id": doc.get("id"),
                "section": _normalize_section_id(doc.get("section") or doc.get("id")),
                "url": doc.get("url"),
                "title": doc.get("title"),
                "score": doc.get("score"),
                "source": doc.get("source"),
            }
        )
    return cleaned


def sanitize_kg_paths(paths: Iterable[Mapping[str, object]] | None) -> list[dict]:
    cleaned: list[dict] = []
    for path in paths or []:
        if not isinstance(path, Mapping):
            continue
        edges: list[dict] = []
        for edge in path.get("edges") or []:
            if not isinstance(edge, Mapping):
                continue
            source = str(edge.get("source") or "").strip()
            predicate = str(edge.get("predicate") or "").strip()
            target = str(edge.get("target") or "").strip()
            if not source or not predicate or not target:
                continue
            edges.append(
                {
                    "source": source,
                    "predicate": predicate,
                    "target": target,
                }
            )
        if not edges:
            continue

        start_section = _normalize_section_id(path.get("start_section_id")) or str(
            path.get("start_section_id") or ""
        ).strip()
        cleaned.append(
            {
                "path_id": str(path.get("path_id") or "").strip(),
                "start_section_id": start_section,
                "edges": edges,
                "graph_iri": path.get("graph_iri"),
                "confidence": path.get("confidence"),
            }
        )
    return sorted(
        cleaned,
        key=lambda item: (
            str(item.get("path_id") or ""),
            str(item.get("start_section_id") or ""),
        ),
    )


def sanitize_kg_expansions(expansions: Iterable[Mapping[str, object]] | None) -> list[dict]:
    cleaned: list[dict] = []
    for snippet in expansions or []:
        if not isinstance(snippet, Mapping):
            continue
        section_id = _normalize_section_id(snippet.get("section_id"))
        if not section_id:
            continue
        related_sections: set[str] = set()
        for related in snippet.get("related_sections") or []:
            norm = _normalize_section_id(related)
            if norm:
                related_sections.add(norm)
        cleaned.append(
            {
                "section_id": section_id,
                "text": str(snippet.get("text") or "").strip(),
                "source": str(snippet.get("source") or "").strip(),
                "paths": sanitize_kg_paths(snippet.get("paths")),  # type: ignore[arg-type]
                "related_sections": sorted(related_sections),
            }
        )
    return sorted(cleaned, key=lambda item: str(item.get("section_id") or ""))


__all__ = [
    "sanitize_citations",
    "sanitize_kg_expansions",
    "sanitize_kg_paths",
    "sanitize_retrieved_docs",
]
