from __future__ import annotations

"""Trace pack contract for per-answer explainability artifacts."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from earCrawler.rag.pipeline import _normalize_section_id


@dataclass(frozen=True, slots=True)
class TraceIssue:
    code: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}


@dataclass(frozen=True, slots=True)
class TracePack:
    trace_id: str
    question_hash: str
    answer_text: str
    label: str
    section_quotes: list[dict[str, object]]
    kg_paths: list[dict[str, object]]
    provenance_hash: str
    citations: list[dict[str, object]]
    retrieval_metadata: list[dict[str, object]]
    run_provenance: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "question_hash": self.question_hash,
            "answer_text": self.answer_text,
            "label": self.label,
            "section_quotes": list(self.section_quotes),
            "kg_paths": list(self.kg_paths),
            "provenance_hash": self.provenance_hash,
            "citations": list(self.citations),
            "retrieval_metadata": list(self.retrieval_metadata),
            "run_provenance": dict(self.run_provenance),
        }


def _as_str(value: object | None) -> str:
    return str(value or "").strip()


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


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_section_quotes(section_quotes: Sequence[Mapping[str, object]] | None) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in section_quotes or []:
        section_id = _normalize_section_id(row.get("section_id"))
        quote = _as_str(row.get("quote"))
        if not section_id or not quote:
            continue
        source_url = _as_str(row.get("source_url")) or None
        score = _as_optional_float(row.get("score"))
        normalized.append(
            {
                "section_id": section_id,
                "quote": quote,
                "source_url": source_url,
                "score": score,
            }
        )
    return sorted(
        normalized,
        key=lambda item: (
            str(item.get("section_id") or ""),
            str(item.get("quote") or ""),
            str(item.get("source_url") or ""),
            float(item.get("score")) if item.get("score") is not None else -1.0,
        ),
    )


def _normalize_kg_paths(kg_paths: Sequence[Mapping[str, object]] | None) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for path in kg_paths or []:
        path_id = _as_str(path.get("path_id"))
        edges: list[dict[str, str]] = []
        for edge in path.get("edges") or []:
            if not isinstance(edge, Mapping):
                continue
            source = _as_str(edge.get("source"))
            predicate = _as_str(edge.get("predicate"))
            target = _as_str(edge.get("target"))
            if not source or not predicate or not target:
                continue
            edges.append({"source": source, "predicate": predicate, "target": target})
        if not path_id or not edges:
            continue
        normalized.append(
            {
                "path_id": path_id,
                "edges": sorted(
                    edges,
                    key=lambda edge: (
                        edge["source"],
                        edge["predicate"],
                        edge["target"],
                    ),
                ),
            }
        )
    return sorted(normalized, key=lambda item: str(item.get("path_id") or ""))


def _normalize_citations(citations: Sequence[Mapping[str, object]] | None) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in citations or []:
        section_id = _normalize_section_id(row.get("section_id"))
        if not section_id:
            continue
        normalized.append(
            {
                "section_id": section_id,
                "quote": _as_str(row.get("quote")),
                "span_id": _as_str(row.get("span_id")),
                "source": _as_str(row.get("source")),
            }
        )
    return sorted(
        normalized,
        key=lambda item: (
            str(item.get("section_id") or ""),
            str(item.get("quote") or ""),
            str(item.get("span_id") or ""),
            str(item.get("source") or ""),
        ),
    )


def _normalize_retrieval_metadata(
    retrieval_metadata: Sequence[Mapping[str, object]] | None,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in retrieval_metadata or []:
        doc_id = _as_str(row.get("id"))
        section = _normalize_section_id(row.get("section") or row.get("id"))
        if not doc_id and not section:
            continue
        normalized.append(
            {
                "id": doc_id or section,
                "section": section,
                "score": _as_optional_float(row.get("score")),
                "source": _as_str(row.get("source")),
                "url": _as_str(row.get("url")),
                "title": _as_str(row.get("title")),
            }
        )
    return sorted(
        normalized,
        key=lambda item: (
            str(item.get("id") or ""),
            str(item.get("section") or ""),
            float(item.get("score")) if item.get("score") is not None else -1.0,
        ),
    )


def _normalize_run_provenance(
    run_provenance: Mapping[str, object] | None,
) -> dict[str, object]:
    if not isinstance(run_provenance, Mapping):
        return {}

    scalar_fields: tuple[str, ...] = (
        "snapshot_id",
        "snapshot_sha256",
        "corpus_digest",
        "index_path",
        "index_sha256",
        "index_meta_path",
        "index_meta_sha256",
        "index_meta_schema_version",
        "index_build_timestamp_utc",
        "embedding_model",
        "llm_provider",
        "llm_model",
    )
    normalized: dict[str, object] = {}
    for key in scalar_fields:
        value = _as_str(run_provenance.get(key))
        if value:
            normalized[key] = value
    return normalized


def canonical_provenance_payload(pack: Mapping[str, object]) -> dict[str, object]:
    """Return canonical evidence payload used to compute provenance_hash."""

    return {
        "section_quotes": _normalize_section_quotes(pack.get("section_quotes")),  # type: ignore[arg-type]
        "kg_paths": _normalize_kg_paths(pack.get("kg_paths")),  # type: ignore[arg-type]
        "citations": _normalize_citations(pack.get("citations")),  # type: ignore[arg-type]
        "retrieval_metadata": _normalize_retrieval_metadata(
            pack.get("retrieval_metadata")  # type: ignore[arg-type]
        ),
        "run_provenance": _normalize_run_provenance(
            pack.get("run_provenance")  # type: ignore[arg-type]
        ),
    }


def provenance_hash(pack: Mapping[str, object]) -> str:
    payload = canonical_provenance_payload(pack)
    blob = _canonical_json(payload)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def normalize_trace_pack(pack: Mapping[str, object]) -> dict[str, object]:
    section_quotes = _normalize_section_quotes(pack.get("section_quotes"))  # type: ignore[arg-type]
    kg_paths = _normalize_kg_paths(pack.get("kg_paths"))  # type: ignore[arg-type]
    citations = _normalize_citations(pack.get("citations"))  # type: ignore[arg-type]
    retrieval_metadata = _normalize_retrieval_metadata(
        pack.get("retrieval_metadata")  # type: ignore[arg-type]
    )
    run_provenance = _normalize_run_provenance(
        pack.get("run_provenance")  # type: ignore[arg-type]
    )
    normalized: dict[str, object] = {
        "trace_id": _as_str(pack.get("trace_id")),
        "question_hash": _as_str(pack.get("question_hash")),
        "answer_text": _as_str(pack.get("answer_text")),
        "label": _as_str(pack.get("label")),
        "section_quotes": section_quotes,
        "kg_paths": kg_paths,
        "citations": citations,
        "retrieval_metadata": retrieval_metadata,
        "run_provenance": run_provenance,
    }
    normalized["provenance_hash"] = _as_str(pack.get("provenance_hash")) or provenance_hash(
        normalized
    )
    return normalized


def validate_trace_pack(
    pack: Mapping[str, object],
    *,
    require_kg_paths: bool = False,
    require_run_provenance: bool = False,
) -> list[TraceIssue]:
    normalized = normalize_trace_pack(pack)
    issues: list[TraceIssue] = []

    if not normalized["trace_id"]:
        issues.append(TraceIssue("missing", "trace_id", "trace_id is required"))
    if not normalized["question_hash"]:
        issues.append(TraceIssue("missing", "question_hash", "question_hash is required"))
    if not normalized["answer_text"]:
        issues.append(TraceIssue("missing", "answer_text", "answer_text is required"))
    if not normalized["label"]:
        issues.append(TraceIssue("missing", "label", "label is required"))

    section_quotes = normalized["section_quotes"]
    if not isinstance(section_quotes, list) or not section_quotes:
        issues.append(
            TraceIssue(
                "missing",
                "section_quotes",
                "section_quotes must contain at least one quoted section",
            )
        )

    kg_paths = normalized["kg_paths"]
    if require_kg_paths and (not isinstance(kg_paths, list) or not kg_paths):
        issues.append(
            TraceIssue(
                "missing",
                "kg_paths",
                "kg_paths must contain at least one structured path for this item",
            )
        )

    run_provenance = normalized["run_provenance"]
    if require_run_provenance:
        required_provenance_fields = (
            "snapshot_id",
            "snapshot_sha256",
            "corpus_digest",
            "index_path",
            "embedding_model",
        )
        for field in required_provenance_fields:
            value = _as_str(run_provenance.get(field)) if isinstance(run_provenance, Mapping) else ""
            if not value:
                issues.append(
                    TraceIssue(
                        "missing",
                        f"run_provenance.{field}",
                        f"run_provenance.{field} is required",
                    )
                )

    provided_hash = _as_str(pack.get("provenance_hash"))
    expected_hash = provenance_hash(normalized)
    if not provided_hash:
        issues.append(
            TraceIssue("missing", "provenance_hash", "provenance_hash is required")
        )
    elif provided_hash != expected_hash:
        issues.append(
            TraceIssue(
                "invalid",
                "provenance_hash",
                "provenance_hash does not match canonical evidence payload",
            )
        )

    return issues


__all__ = [
    "TraceIssue",
    "TracePack",
    "canonical_provenance_payload",
    "normalize_trace_pack",
    "provenance_hash",
    "validate_trace_pack",
]
