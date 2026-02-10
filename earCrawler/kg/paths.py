from __future__ import annotations

"""Structured KG expansion models used by RAG outputs and eval artifacts."""

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


def _as_str(value: object | None) -> str:
    return str(value or "").strip()


def _as_optional_str(value: object | None) -> str | None:
    text = _as_str(value)
    return text or None


def _as_optional_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = _as_str(value)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class KGPathEdge:
    source: str
    predicate: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "predicate": self.predicate,
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "KGPathEdge":
        return cls(
            source=_as_str(data.get("source")),
            predicate=_as_str(data.get("predicate")),
            target=_as_str(data.get("target")),
        )


@dataclass(frozen=True, slots=True)
class KGPath:
    path_id: str
    start_section_id: str
    edges: list[KGPathEdge]
    graph_iri: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path_id": self.path_id,
            "start_section_id": self.start_section_id,
            "edges": [edge.to_dict() for edge in self.edges],
            "graph_iri": self.graph_iri,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "KGPath":
        raw_edges = data.get("edges")
        edges: list[KGPathEdge] = []
        if isinstance(raw_edges, Sequence):
            for item in raw_edges:
                if isinstance(item, Mapping):
                    edges.append(KGPathEdge.from_dict(item))
        start_section_id = _as_str(data.get("start_section_id"))
        graph_iri = _as_optional_str(data.get("graph_iri"))
        return cls(
            path_id=_as_str(data.get("path_id"))
            or stable_path_id(start_section_id=start_section_id, edges=edges, graph_iri=graph_iri),
            start_section_id=start_section_id,
            edges=edges,
            graph_iri=graph_iri,
            confidence=_as_optional_float(data.get("confidence")),
        )


@dataclass(frozen=True, slots=True)
class KGExpansionSnippet:
    section_id: str
    text: str
    source: str
    paths: list[KGPath]
    related_sections: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "text": self.text,
            "source": self.source,
            "paths": [path.to_dict() for path in self.paths],
            "related_sections": list(self.related_sections),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "KGExpansionSnippet":
        raw_paths = data.get("paths")
        paths: list[KGPath] = []
        if isinstance(raw_paths, Sequence):
            for item in raw_paths:
                if isinstance(item, Mapping):
                    paths.append(KGPath.from_dict(item))

        raw_related = data.get("related_sections")
        related_sections: list[str] = []
        if isinstance(raw_related, Sequence):
            for value in raw_related:
                text = _as_str(value)
                if text:
                    related_sections.append(text)

        return cls(
            section_id=_as_str(data.get("section_id")),
            text=_as_str(data.get("text")),
            source=_as_str(data.get("source")) or "unknown",
            paths=paths,
            related_sections=sorted(set(related_sections)),
        )


def stable_path_id(
    *,
    start_section_id: str,
    edges: Sequence[KGPathEdge],
    graph_iri: str | None,
) -> str:
    payload = {
        "start_section_id": _as_str(start_section_id),
        "graph_iri": _as_optional_str(graph_iri),
        "edges": [edge.to_dict() for edge in edges],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(blob.encode("utf-8")).hexdigest()


__all__ = [
    "KGPathEdge",
    "KGPath",
    "KGExpansionSnippet",
    "stable_path_id",
]
