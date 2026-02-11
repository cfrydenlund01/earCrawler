from __future__ import annotations

"""Dataset-driven evaluation using the RAG pipeline + remote LLM providers."""

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from collections import Counter

from api_clients.llm_client import LLMProviderError
from eval.validate_datasets import ensure_valid_datasets
from earCrawler.audit.hitl_events import decision_template
from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.eval.citation_metrics import (
    CitationScore,
    extract_ground_truth_sections,
    extract_predicted_sections,
    score_citations,
)
from earCrawler.eval.label_inference import infer_label
from earCrawler.rag.output_schema import DEFAULT_ALLOWED_LABELS
from earCrawler.rag.pipeline import _normalize_section_id, answer_with_rag
from earCrawler.security.data_egress import hash_text
from earCrawler.trace.trace_pack import (
    normalize_trace_pack,
    provenance_hash as trace_provenance_hash,
    validate_trace_pack,
)

_ALLOWED_LABELS = DEFAULT_ALLOWED_LABELS


def _normalize_pred_label(
    pred_label_raw: str,
    *,
    task: str,
    question: str,
    answer: str,
    justification: str | None,
) -> tuple[str, str | None]:
    label = (pred_label_raw or "").strip().lower() or "unknown"
    if label not in _ALLOWED_LABELS:
        inferred = infer_label(answer)
        if inferred in _ALLOWED_LABELS:
            return inferred, f"fallback_infer_label_from_answer({label})"
        return label, None

    question_l = (question or "").lower()
    justification_l = (justification or "").lower()

    if "license exception" in question_l or "license exception" in justification_l:
        if task == "entity_obligation":
            if label in {
                "exception_applies",
                "no_license_required",
                "permitted_with_license",
                "license_required",
            }:
                return "permitted", "normalized_by_license_exception_signal(entity_obligation)"
        else:
            if label in {
                "permitted",
                "no_license_required",
                "permitted_with_license",
                "license_required",
            }:
                return "exception_applies", "normalized_by_license_exception_signal"

    if task == "entity_obligation" and "without a license" in question_l:
        if label == "license_required":
            return "permitted_with_license", "normalized_license_required_to_permitted_with_license"

    if task == "ear_compliance" and ("need a license" in question_l or "license required" in question_l):
        if label == "prohibited":
            return "license_required", "normalized_prohibited_to_license_required"

    return label, None


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_dataset(manifest: dict, dataset_id: str, manifest_path: Path) -> tuple[dict, Path]:
    for entry in manifest.get("datasets", []):
        if entry.get("id") == dataset_id:
            file = Path(entry["file"])
            if file.is_absolute():
                return entry, file
            if file.exists():
                return entry, file
            candidate = manifest_path.parent / file
            return entry, candidate
    raise ValueError(f"Dataset not found: {dataset_id}")


def _iter_items(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def _safe_name(value: str) -> str:
    return value.replace("/", "-").replace(":", "-")


_ANSWER_SCORE_MODES = ("semantic", "normalized", "exact")
_ABLATION_MODES = ("faiss_only", "faiss_plus_kg")
_DEFAULT_FALLBACK_MAX_USES = 0


def _fallback_code(reason: str | None) -> str | None:
    value = (reason or "").strip()
    if not value:
        return None
    if value.startswith("fallback_infer_label_from_answer("):
        return "infer_label_from_answer"
    if value == "normalized_by_license_exception_signal(entity_obligation)":
        return "normalized_by_license_exception_signal_entity_obligation"
    if value == "normalized_by_license_exception_signal":
        return "normalized_by_license_exception_signal"
    if value == "normalized_license_required_to_permitted_with_license":
        return "normalized_license_required_to_permitted_with_license"
    if value == "normalized_prohibited_to_license_required":
        return "normalized_prohibited_to_license_required"
    return f"unknown_normalization:{value}"


def _fallback_policy() -> list[dict[str, str]]:
    return [
        {
            "fallback": "infer_label_from_answer",
            "decision": "keep_with_counter",
            "reason": "Legacy model outputs may emit unknown labels; keep inference but surface usage.",
        },
        {
            "fallback": "normalized_by_license_exception_signal_entity_obligation",
            "decision": "keep_with_counter",
            "reason": "Task-specific label normalization remains for backward compatibility.",
        },
        {
            "fallback": "normalized_by_license_exception_signal",
            "decision": "keep_with_counter",
            "reason": "License-exception heuristic remains enabled but is now explicit in strictness metrics.",
        },
        {
            "fallback": "normalized_license_required_to_permitted_with_license",
            "decision": "keep_with_counter",
            "reason": "Question-form normalization remains enabled but counted.",
        },
        {
            "fallback": "normalized_prohibited_to_license_required",
            "decision": "keep_with_counter",
            "reason": "EAR-compliance label normalization remains enabled but counted.",
        },
        {
            "fallback": "proxy_citations_from_used_sections",
            "decision": "removed",
            "reason": "Citation scoring no longer infers citations from retrieval sections.",
        },
    ]


def _normalize_answer_text(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    value = re.sub(r"^(answer|final answer)\s*:\s*", "", value, flags=re.IGNORECASE)
    value = value.casefold()
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(" \t\n\r\"'`")
    value = value.strip(" .,:;!?")
    return value


def _semantic_match_ratio(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def _answer_is_correct(
    gt_answer: str,
    pred_answer: str,
    *,
    mode: str,
    semantic_threshold: float = 0.6,
) -> bool:
    if not gt_answer:
        return False
    if not pred_answer:
        return False
    if mode == "exact":
        return pred_answer == gt_answer
    if mode == "normalized":
        return _normalize_answer_text(pred_answer) == _normalize_answer_text(gt_answer)
    if mode == "semantic":
        return _semantic_match_ratio(pred_answer, gt_answer) >= semantic_threshold
    raise ValueError(f"Unknown answer score mode: {mode}")


def _flatten_reference_sections(manifest: Mapping[str, object]) -> set[str]:
    refs = manifest.get("references") or {}
    sections = refs.get("sections") or {}
    flattened: set[str] = set()
    if isinstance(sections, Mapping):
        for values in sections.values():
            if isinstance(values, Mapping):
                iter_values = values.get("sections") or values.get("spans") or values.values()
            else:
                iter_values = values
            if not isinstance(iter_values, Iterable):
                continue
            for sec in iter_values:
                norm = _normalize_section_id(sec)
                if norm:
                    flattened.add(norm)
    return flattened


def _parse_reference_sections(
    manifest: Mapping[str, object],
) -> tuple[set[str], set[str]]:
    refs = manifest.get("references") or {}
    sections = refs.get("sections") or {}
    allowed: set[str] = set()
    reserved: set[str] = set()
    if isinstance(sections, Mapping):
        for values in sections.values():
            if isinstance(values, Mapping):
                iter_values = (
                    values.get("sections")
                    or values.get("spans")
                    or values.get("values")
                    or values.values()
                )
            else:
                iter_values = values
            if not isinstance(iter_values, Iterable):
                continue
            for sec in iter_values or []:
                reserved_flag = False
                raw = sec
                if isinstance(sec, Mapping):
                    reserved_flag = bool(sec.get("reserved"))
                    raw = (
                        sec.get("id")
                        or sec.get("section_id")
                        or sec.get("span_id")
                        or sec.get("value")
                        or sec.get("section")
                    )
                norm = _normalize_section_id(raw)
                if not norm:
                    continue
                allowed.add(norm)
                if reserved_flag:
                    reserved.add(norm)
    return allowed, reserved


def _sanitize_citations(citations: Iterable[Mapping[str, object]] | None) -> list[dict]:
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


def _sanitize_retrieved_docs(docs: Iterable[Mapping[str, object]] | None) -> list[dict]:
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


def _sanitize_kg_paths(paths: Iterable[Mapping[str, object]] | None) -> list[dict]:
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


def _sanitize_kg_expansions(expansions: Iterable[Mapping[str, object]] | None) -> list[dict]:
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
                "paths": _sanitize_kg_paths(snippet.get("paths")),  # type: ignore[arg-type]
                "related_sections": sorted(related_sections),
            }
        )
    return sorted(cleaned, key=lambda item: str(item.get("section_id") or ""))


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_index_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _sanitize_trace_run_provenance(provenance: Mapping[str, object]) -> dict[str, str]:
    fields: tuple[str, ...] = (
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
    sanitized: dict[str, str] = {}
    for field in fields:
        value = str(provenance.get(field) or "").strip()
        if value:
            sanitized[field] = value
    return sanitized


def _collect_trace_run_provenance(*, llm_provider: str, llm_model: str) -> dict[str, str]:
    index_override = str(os.getenv("EARCRAWLER_FAISS_INDEX") or "").strip()
    index_path = Path(index_override) if index_override else Path("data") / "faiss" / "index.faiss"
    model_override = str(os.getenv("EARCRAWLER_FAISS_MODEL") or "").strip() or "all-MiniLM-L12-v2"
    meta_path = index_path.with_suffix(".meta.json")
    meta = _load_index_meta(meta_path) or {}
    snapshot = meta.get("snapshot") if isinstance(meta.get("snapshot"), Mapping) else {}

    provenance: dict[str, object] = {
        "snapshot_id": str(snapshot.get("snapshot_id") or "unknown").strip() or "unknown",
        "snapshot_sha256": str(snapshot.get("snapshot_sha256") or "unknown").strip() or "unknown",
        "corpus_digest": str(meta.get("corpus_digest") or "unknown").strip() or "unknown",
        "index_path": str(index_path.resolve()),
        "embedding_model": str(meta.get("embedding_model") or model_override or "unknown").strip() or "unknown",
        "llm_provider": str(llm_provider or "unknown").strip() or "unknown",
        "llm_model": str(llm_model or "unknown").strip() or "unknown",
    }
    index_sha = _sha256_file(index_path)
    if index_sha:
        provenance["index_sha256"] = index_sha
    if meta_path.exists():
        provenance["index_meta_path"] = str(meta_path.resolve())
        meta_sha = _sha256_file(meta_path)
        if meta_sha:
            provenance["index_meta_sha256"] = meta_sha
    schema_version = str(meta.get("schema_version") or "").strip()
    if schema_version:
        provenance["index_meta_schema_version"] = schema_version
    build_ts = str(meta.get("build_timestamp_utc") or "").strip()
    if build_ts:
        provenance["index_build_timestamp_utc"] = build_ts

    return _sanitize_trace_run_provenance(provenance)


def _retrieval_id_set(result: Mapping[str, object]) -> set[str]:
    ids: set[str] = set()
    for sec in result.get("used_sections") or []:
        norm = _normalize_section_id(sec)
        if norm:
            ids.add(norm)
    for doc in result.get("retrieved_docs") or []:
        norm_doc = _normalize_section_id(doc.get("section") or doc.get("id"))
        if norm_doc:
            ids.add(norm_doc)
    return ids


def _evaluate_citation_quality(
    result: Mapping[str, object], reference_sections: set[str] | None
) -> dict[str, object]:
    citations = result.get("citations") or []
    total_citations = len(citations)
    items_with_citations = 1 if total_citations else 0

    retrieval_ids = _retrieval_id_set(result)
    errors: list[str] = []
    valid_citations = 0
    supported_citations = 0
    overclaim = False

    if total_citations == 0:
        errors.append("missing")

    for cit in citations:
        section_norm = _normalize_section_id(cit.get("section_id"))
        canonical = bool(section_norm and section_norm.upper().startswith("EAR-"))
        if not canonical:
            errors.append("invalid_format")
        else:
            if reference_sections is not None and section_norm not in reference_sections:
                errors.append("not_in_references")
            else:
                valid_citations += 1
        if section_norm in retrieval_ids:
            supported_citations += 1
        else:
            if total_citations:
                overclaim = True
            errors.append("not_in_retrieval")

    return {
        "ok": not errors,
        "errors": sorted(set(errors)),
        "counts": {
            "items": 1,
            "items_with_citations": items_with_citations,
            "total_citations": total_citations,
            "valid_citations": valid_citations,
            "supported_citations": supported_citations,
            "items_overclaim": 1 if overclaim else 0,
        },
    }


def _finalize_citation_metrics(counts: Mapping[str, int], num_items: int) -> dict[str, float]:
    total_citations = counts.get("total_citations", 0) or 0
    items_with_citations = counts.get("items_with_citations", 0) or 0
    supported_citations = counts.get("supported_citations", 0) or 0
    valid_citations = counts.get("valid_citations", 0) or 0
    items_overclaim = counts.get("items_overclaim", 0) or 0

    presence_rate = items_with_citations / num_items if num_items else 0.0
    valid_id_rate = valid_citations / total_citations if total_citations else 0.0
    supported_rate = supported_citations / total_citations if total_citations else 0.0
    overclaim_rate = items_overclaim / num_items if num_items else 0.0

    return {
        "presence_rate": presence_rate,
        "valid_id_rate": valid_id_rate,
        "supported_rate": supported_rate,
        "overclaim_rate": overclaim_rate,
        "counts": {
            "items_with_citations": items_with_citations,
            "total_citations": total_citations,
            "valid_citations": valid_citations,
            "supported_citations": supported_citations,
            "items_overclaim": items_overclaim,
        },
    }


def _aggregate_citation_scores(scores: Sequence[CitationScore]) -> dict[str, object]:
    if not scores:
        return {
            "macro": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "micro": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0},
            "error_counts": {},
            "items_scored": 0,
        }

    total_tp = sum(s.tp for s in scores)
    total_fp = sum(s.fp for s in scores)
    total_fn = sum(s.fn for s in scores)
    total_gt = total_tp + total_fn

    def _micro_precision() -> float:
        if total_tp + total_fp == 0:
            return 1.0 if total_gt == 0 else 0.0
        return total_tp / (total_tp + total_fp)

    def _micro_recall() -> float:
        if total_gt == 0:
            return 1.0
        return total_tp / total_gt

    micro_precision = _micro_precision()
    micro_recall = _micro_recall()
    denom = micro_precision + micro_recall
    micro_f1 = (
        (2 * micro_precision * micro_recall / denom)
        if denom
        else (1.0 if (total_tp == 0 and total_fp == 0 and total_fn == 0) else 0.0)
    )

    macro_precision = sum(s.precision for s in scores) / len(scores)
    macro_recall = sum(s.recall for s in scores) / len(scores)
    macro_denom = macro_precision + macro_recall
    macro_f1 = (
        (2 * macro_precision * macro_recall / macro_denom)
        if macro_denom
        else (1.0 if all((s.tp + s.fp + s.fn) == 0 for s in scores) else 0.0)
    )

    error_counts: Counter[str] = Counter()
    for s in scores:
        for err in s.errors:
            code = str(err.get("code") or "unknown")
            error_counts[code] += 1

    return {
        "macro": {"precision": macro_precision, "recall": macro_recall, "f1": macro_f1},
        "micro": {
            "precision": micro_precision,
            "recall": micro_recall,
            "f1": micro_f1,
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        },
        "error_counts": dict(sorted(error_counts.items())),
        "items_scored": len(scores),
    }


def _make_trace_id(dataset_id: str, item_id: str, question: str) -> str:
    seed = f"{dataset_id}\n{item_id}\n{question}"
    return f"trace-{hash_text(seed)[:24]}"


def _is_multihop_item(item: Mapping[str, object]) -> bool:
    if bool(item.get("multihop")):
        return True
    tags = item.get("tags") or []
    if isinstance(tags, Sequence) and not isinstance(tags, (str, bytes)) and any(
        str(tag).strip().lower() == "multihop" for tag in tags
    ):
        return True

    evidence = item.get("evidence") or {}
    expected_sections: set[str] = set()
    for sec in item.get("ear_sections") or []:
        norm = _normalize_section_id(sec)
        if norm:
            expected_sections.add(norm)
    for span in evidence.get("doc_spans") or []:
        if not isinstance(span, Mapping):
            continue
        norm = _normalize_section_id(span.get("span_id"))
        if norm:
            expected_sections.add(norm)
    if len(expected_sections) >= 2:
        return True

    kg_paths = evidence.get("kg_paths") or []
    return bool(kg_paths)


def _slice_definition(
    dataset_meta: Mapping[str, object], *, multihop_only: bool
) -> dict[str, object]:
    definition = dict(dataset_meta.get("slice") or {})
    if multihop_only and "selector" not in definition:
        definition["selector"] = {
            "type": "runtime_filter",
            "rule": ">=2 expected sections OR >=1 kg_path reference",
        }
    return definition


def _build_trace_pack(
    *,
    trace_id: str,
    question: str,
    answer_text: str,
    label: str,
    citations: Sequence[Mapping[str, object]] | None,
    retrieved_docs: Sequence[Mapping[str, object]] | None,
    kg_paths_used: Sequence[Mapping[str, object]] | None,
    run_provenance: Mapping[str, object] | None,
) -> dict[str, object]:
    doc_by_section: dict[str, Mapping[str, object]] = {}
    for doc in retrieved_docs or []:
        if not isinstance(doc, Mapping):
            continue
        section = _normalize_section_id(doc.get("section") or doc.get("id"))
        if section:
            doc_by_section.setdefault(section, doc)

    section_quotes: list[dict[str, object]] = []
    for citation in citations or []:
        if not isinstance(citation, Mapping):
            continue
        section_id = _normalize_section_id(citation.get("section_id"))
        quote = str(citation.get("quote") or "").strip()
        if not section_id or not quote:
            continue
        doc_meta = doc_by_section.get(section_id, {})
        section_quotes.append(
            {
                "section_id": section_id,
                "quote": quote,
                "source_url": doc_meta.get("url") if isinstance(doc_meta, Mapping) else None,
                "score": doc_meta.get("score") if isinstance(doc_meta, Mapping) else None,
            }
        )

    trace_pack: dict[str, object] = {
        "trace_id": trace_id,
        "question_hash": hash_text(question),
        "answer_text": answer_text,
        "label": label,
        "section_quotes": section_quotes,
        "kg_paths": _sanitize_kg_paths(kg_paths_used),
        "citations": _sanitize_citations(citations),
        "retrieval_metadata": _sanitize_retrieved_docs(retrieved_docs),
        "run_provenance": _sanitize_trace_run_provenance(run_provenance or {}),
    }
    trace_pack["provenance_hash"] = trace_provenance_hash(trace_pack)
    return normalize_trace_pack(trace_pack)


def _write_answer_artifacts(
    results: Sequence[Mapping[str, object]],
    *,
    dataset_id: str,
    run_id: str,
    base_dir: Path,
    provider: str | None,
    model: str | None,
    run_meta: Mapping[str, object],
) -> list[Path]:
    base = base_dir / run_id / "answers" / dataset_id
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for idx, result in enumerate(results):
        item_id = result.get("id") or f"item-{idx+1:04d}"
        safe_item = _safe_name(str(item_id))
        artifact = {
            "dataset_id": dataset_id,
            "item_id": str(item_id),
            "question": result.get("question"),
            "label": result.get("pred_label"),
            "answer": result.get("pred_answer"),
            "justification": result.get("justification"),
            "citations": result.get("citations") or [],
            "retrieved_docs": result.get("retrieved_docs") or [],
            "kg_paths_used": result.get("kg_paths_used") or [],
            "kg_related_sections": result.get("kg_related_sections") or [],
            "kg_expansion_snippets": result.get("kg_expansions") or [],
            "trace_id": result.get("trace_id"),
            "provider": provider,
            "model": model,
            "run_id": run_id,
            "run_meta": dict(run_meta),
        }
        out_path = base / f"{safe_item}.answer.json"
        out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(out_path)
    return written


def _write_trace_pack_artifacts(
    trace_packs: Mapping[str, Mapping[str, object]],
    *,
    dataset_id: str,
    run_id: str,
    base_dir: Path,
) -> dict[str, Path]:
    base = base_dir / run_id / "trace_packs" / dataset_id
    base.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for item_id in sorted(trace_packs.keys()):
        safe_item = _safe_name(str(item_id))
        out_path = base / f"{safe_item}.trace.json"
        out_path.write_text(
            json.dumps(trace_packs[item_id], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written[item_id] = out_path
    return written


def _write_hitl_templates(
    *,
    out_dir: Path,
    dataset_id: str,
    run_id: str,
    results: Sequence[Mapping[str, object]],
) -> list[Path]:
    base = out_dir / run_id / "hitl_templates" / dataset_id
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for idx, result in enumerate(results):
        item_id = str(result.get("id") or f"item-{idx+1:04d}")
        trace_id = str(result.get("trace_id") or "")
        question_hash = str(result.get("question_hash") or "")
        initial_label = str(result.get("pred_label") or "")
        answer_text = str(result.get("answer_text") or "")
        provenance_hash = str(result.get("provenance_hash") or "")
        template = decision_template(
            trace_id=trace_id,
            dataset_id=dataset_id,
            item_id=item_id,
            question_hash=question_hash,
            initial_label=initial_label,
            initial_answer=answer_text,
            provenance_hash=provenance_hash,
        )
        path = base / f"{_safe_name(item_id)}.hitl.json"
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)
    return written


def evaluate_dataset(
    dataset_id: str,
    *,
    manifest_path: Path,
    llm_provider: str | None,
    llm_model: str | None,
    top_k: int,
    max_items: int | None,
    out_json: Path,
    out_md: Path,
    answer_score_mode: str = "semantic",
    semantic_threshold: float = 0.6,
    semantic: bool = False,
    ablation: str | None = None,
    kg_expansion: bool | None = None,
    multihop_only: bool = False,
    emit_hitl_template: Path | None = None,
    trace_pack_require_kg_paths: bool = False,
    trace_pack_required_threshold: float | None = None,
    fallback_max_uses: int | None = _DEFAULT_FALLBACK_MAX_USES,
) -> tuple[Path, Path]:
    manifest = _load_manifest(manifest_path)
    dataset_refs = manifest.get("references") or {}
    kg_digest = (manifest.get("kg_state", {}) or {}).get("digest")
    dataset_meta, data_path = _resolve_dataset(manifest, dataset_id, manifest_path)
    reference_sections, reserved_sections = _parse_reference_sections(manifest)

    cfg = get_llm_config(provider_override=llm_provider, model_override=llm_model)
    if not cfg.enable_remote:
        raise RuntimeError(
            "Remote LLMs are disabled. Set EARCRAWLER_REMOTE_LLM_POLICY=allow, "
            "EARCRAWLER_ENABLE_REMOTE_LLM=1, and configure provider keys."
        )
    provider = cfg.provider.provider
    model = cfg.provider.model
    trace_run_provenance = _collect_trace_run_provenance(
        llm_provider=provider,
        llm_model=model,
    )
    run_id = _safe_name(out_json.stem)
    ablation_mode = (ablation or "").strip().lower() or None
    if ablation_mode and ablation_mode not in _ABLATION_MODES:
        raise ValueError(f"Unsupported --ablation: {ablation_mode}")
    kg_expansion_enabled = (
        bool(kg_expansion)
        if kg_expansion is not None
        else (ablation_mode == "faiss_plus_kg" if ablation_mode else None)
    )
    run_meta = {
        "dataset_version": dataset_meta.get("version"),
        "kg_state_digest": kg_digest,
        "manifest_path": str(manifest_path),
        "ablation": ablation_mode,
        "kg_expansion": kg_expansion_enabled,
        "multihop_only": bool(multihop_only),
        "trace_run_provenance": trace_run_provenance,
    }

    results: List[Dict[str, Any]] = []
    latencies: List[float] = []
    citation_counts: Dict[str, int] = {
        "items_with_citations": 0,
        "total_citations": 0,
        "valid_citations": 0,
        "supported_citations": 0,
        "items_overclaim": 0,
    }
    citation_scores: List[CitationScore] = []
    citation_proxy_items = 0
    citation_infra_skipped = 0
    status_counts: Counter[str] = Counter()
    fallback_counts: Counter[str] = Counter()
    fallback_items: list[dict[str, object]] = []

    correct = 0
    answer_total = 0
    label_correct = 0
    label_total = 0
    unanswerable_correct = 0
    unanswerable_total = 0
    grounded_hits = 0
    semantic_hits = 0
    truthiness_items = 0
    output_failures = 0
    total_expected_sections = 0
    total_expected_sections_hit = 0
    multihop_items = 0
    multihop_expected_sections = 0
    multihop_expected_sections_hit = 0
    multihop_kg_path_used = 0

    by_task_raw: Dict[str, Dict[str, float]] = {}
    trace_packs: dict[str, dict[str, object]] = {}
    trace_pack_issues_by_item: dict[str, list[dict[str, str]]] = {}

    mode = (answer_score_mode or "").strip().lower() or "semantic"
    if mode not in _ANSWER_SCORE_MODES:
        raise ValueError(f"Unsupported --answer-score-mode: {mode}")
    if semantic_threshold <= 0 or semantic_threshold > 1:
        raise ValueError("semantic_threshold must be in (0, 1]")
    if fallback_max_uses is not None and fallback_max_uses < 0:
        raise ValueError("fallback_max_uses must be >= 0")

    emitted = 0
    for idx, item in enumerate(_iter_items(data_path)):
        if multihop_only and not _is_multihop_item(item):
            continue
        if max_items is not None and emitted >= max_items:
            break
        emitted += 1
        question = item.get("question", "")
        ground_truth = item.get("ground_truth", {}) or {}
        gt_answer = (ground_truth.get("answer_text") or "").strip()
        gt_label = (ground_truth.get("label") or "").strip().lower()
        task = str(item.get("task", "") or "").strip()
        ear_sections = item.get("ear_sections") or []
        item_id = str(item.get("id") or f"item-{idx+1:04d}")
        item_multihop = _is_multihop_item(item)

        answer: str | None = None
        pred_label = "unknown"
        pred_label_raw = pred_label
        label_norm: str | None = None
        justification: str | None = None
        used_sections: List[str] = []
        retrieved_docs: List[dict] = []
        error: str | None = None
        retrieval_warnings: list[dict[str, object]] = []
        retrieval_empty = False
        retrieval_empty_reason: str | None = None
        output_ok = True
        output_error: dict | None = None
        raw_answer: str | None = None
        status = "ok"
        status_category = "ok"
        item_fallbacks: list[dict[str, str]] = []
        citations: list[dict] | None = None
        evidence_okay: dict | None = None
        assumptions: list[str] | None = None
        citation_span_ids: list[str] | None = None
        kg_paths_used: list[dict] = []
        kg_expansions: list[dict] = []
        kg_related_sections: list[str] = []
        trace_id: str | None = _make_trace_id(dataset_id, item_id, str(question))

        start = time.perf_counter()
        try:
            label_schema = None
            if gt_label in {"true", "false"}:
                label_schema = "truthiness"
            rag_result = answer_with_rag(
                question,
                task=task or None,
                label_schema=label_schema,
                provider=provider,
                model=model,
                top_k=top_k,
                kg_expansion=kg_expansion_enabled,
                strict_retrieval=False,
                strict_output=True,
                trace_id=trace_id,
            )
            raw_answer = rag_result.get("raw_answer")
            output_ok = bool(rag_result.get("output_ok", True))
            output_error = rag_result.get("output_error")
            answer = (rag_result.get("answer") or "").strip() if output_ok else ""
            used_sections = list(rag_result.get("used_sections") or [])
            retrieved_docs = _sanitize_retrieved_docs(rag_result.get("retrieved_docs"))
            retrieval_warnings = list(rag_result.get("retrieval_warnings") or [])
            retrieval_empty = bool(rag_result.get("retrieval_empty"))
            retrieval_empty_reason = rag_result.get("retrieval_empty_reason")
            citations = _sanitize_citations(rag_result.get("citations"))
            evidence_okay = rag_result.get("evidence_okay")
            assumptions = rag_result.get("assumptions")
            citation_span_ids = rag_result.get("citation_span_ids")
            kg_paths_used = _sanitize_kg_paths(rag_result.get("kg_paths_used"))  # type: ignore[arg-type]
            kg_expansions = _sanitize_kg_expansions(rag_result.get("kg_expansions"))  # type: ignore[arg-type]
            kg_related_sections = sorted(
                {
                    sec
                    for snippet in kg_expansions
                    for sec in (snippet.get("related_sections") or [])
                    if isinstance(sec, str) and sec.strip()
                }
            )
            trace_id = rag_result.get("trace_id") or trace_id
            # Prefer structured label from the JSON contract when present.
            justification = (rag_result.get("justification") or "").strip() or None
            if not output_ok:
                status = "failed_output_schema"
                status_category = "model_output_invalid"
                output_failures += 1
                error = (output_error or {}).get("message") if output_error else "invalid_output_schema"
                pred_label = "invalid_output"
                pred_label_raw = pred_label
            else:
                structured_label = (rag_result.get("label") or "").strip().lower()
                if structured_label:
                    pred_label = structured_label
                else:
                    pred_label = infer_label(answer)
                pred_label_raw = pred_label
                pred_label, label_norm = _normalize_pred_label(
                    pred_label_raw,
                    task=task,
                    question=question,
                    answer=answer,
                    justification=justification,
                )
                fallback_code = _fallback_code(label_norm)
                if fallback_code:
                    fallback_counts[fallback_code] += 1
                    item_fallbacks.append(
                        {
                            "code": fallback_code,
                            "detail": str(label_norm),
                        }
                    )
        except LLMProviderError as exc:
            error = str(exc)
            status_category = "infra_error"
            status = "infra_error"
            output_ok = False
        except Exception as exc:  # pragma: no cover - defensive
            error = f"unexpected_error: {exc}"
            status_category = "infra_error"
            status = "infra_error"
            output_ok = False
        end = time.perf_counter()
        latencies.append(end - start)

        grounded = bool(set(ear_sections) & set(used_sections))
        if grounded:
            grounded_hits += 1

        answer_correct = _answer_is_correct(
            gt_answer,
            answer,
            mode=mode,
            semantic_threshold=semantic_threshold,
        )
        if gt_answer and status_category != "infra_error":
            answer_total += 1
            if answer_correct:
                correct += 1

        if semantic and gt_answer and answer and status_category != "infra_error":
            if _semantic_match_ratio(answer, gt_answer) >= semantic_threshold:
                semantic_hits += 1

        if gt_label and status_category != "infra_error":
            label_total += 1
            if pred_label == gt_label:
                label_correct += 1
            if gt_label in {"true", "false"}:
                truthiness_items += 1
        if gt_label == "unanswerable":
            unanswerable_total += 1
            if pred_label == "unanswerable":
                unanswerable_correct += 1
            elif status_category == "ok":
                status_category = "refusal_expected_missing"
        if status_category == "ok" and gt_label and pred_label != gt_label:
            status_category = "model_answer_wrong"

        if task and status_category != "infra_error":
            stats = by_task_raw.setdefault(
                task,
                {
                    "count": 0.0,
                    "answer_correct": 0.0,
                    "label_total": 0.0,
                    "label_correct": 0.0,
                    "grounded_hits": 0.0,
                },
            )
            stats["count"] += 1
            if answer_correct:
                stats["answer_correct"] += 1
            if gt_label:
                stats["label_total"] += 1
                if pred_label == gt_label:
                    stats["label_correct"] += 1
            if grounded:
                stats["grounded_hits"] += 1

        gt_sections = extract_ground_truth_sections(item, dataset_refs)
        pred_sections = extract_predicted_sections({"citations": citations})
        proxy_citations_used = False

        retrieval_ids = _retrieval_id_set(
            {"used_sections": used_sections, "retrieved_docs": retrieved_docs}
        )
        missing_in_retrieval = sorted(gt_sections - retrieval_ids)
        reserved_hits = sorted(sec for sec in pred_sections if sec in reserved_sections)
        not_in_refs = sorted(
            sec for sec in pred_sections if reference_sections and sec not in reference_sections
        )
        invalid_ids = [
            str(cit.get("section_id") or "")
            for cit in citations or []
            if not _normalize_section_id(cit.get("section_id"))
        ]
        fp_sections = sorted(pred_sections - gt_sections)
        fn_sections = sorted(gt_sections - pred_sections)

        citation_errors: list[dict[str, object]] = []
        if invalid_ids:
            citation_errors.append({"code": "invalid_id", "sections": invalid_ids})
        if reserved_hits:
            citation_errors.append({"code": "reserved_cited", "sections": reserved_hits})
        if not_in_refs:
            citation_errors.append({"code": "not_in_references", "sections": not_in_refs})
        if fp_sections:
            citation_errors.append({"code": "not_in_expected", "sections": fp_sections})
        if fn_sections:
            citation_errors.append({"code": "missing_expected", "sections": fn_sections})
        if missing_in_retrieval:
            citation_errors.append({"code": "missing_in_retrieval", "sections": missing_in_retrieval})

        citation_score = score_citations(pred_sections, gt_sections, errors=citation_errors)
        citation_not_scored = status_category == "infra_error"
        if citation_not_scored:
            citation_infra_skipped += 1
        else:
            citation_scores.append(citation_score)
            for err in citation_errors:
                code = str(err.get("code") or "unknown")
                citation_counts[code] = citation_counts.get(code, 0) + 1

        if status_category == "ok" and missing_in_retrieval and gt_sections:
            status_category = "retrieval_miss_gt_section"
        if status_category == "ok" and (
            citation_score.fp or citation_score.fn or reserved_hits or invalid_ids or not_in_refs
        ):
            status_category = "citation_wrong"

        if status != "failed_output_schema":
            status = status_category
        status_counts[status_category] += 1

        expected_hit = len(gt_sections & pred_sections)
        total_expected_sections += len(gt_sections)
        total_expected_sections_hit += expected_hit
        if item_multihop:
            multihop_items += 1
            multihop_expected_sections += len(gt_sections)
            multihop_expected_sections_hit += expected_hit
            if kg_paths_used:
                multihop_kg_path_used += 1

        result_entry = {
            "id": item_id,
            "question": question,
            "task": task,
            "ground_truth_answer": gt_answer,
            "ground_truth_label": gt_label,
            "pred_answer": answer,
            "answer_text": answer,
            "pred_label_raw": pred_label_raw,
            "pred_label": pred_label,
            "pred_label_normalization": label_norm,
            "fallbacks": item_fallbacks,
            "fallbacks_used": len(item_fallbacks),
            "grounded": grounded,
            "expected_sections": ear_sections,
            "used_sections": used_sections,
            "retrieved_docs": retrieved_docs,
            "trace_id": trace_id,
            "question_hash": hash_text(question),
            "justification": justification,
            "evidence": item.get("evidence"),
            "error": error,
            "status": status,
            "status_category": status_category,
            "output_ok": output_ok,
            "output_error": output_error,
            "raw_answer": raw_answer,
            "citations": citations,
            "evidence_okay": evidence_okay,
            "assumptions": assumptions,
            "citation_span_ids": citation_span_ids,
            "kg_paths_used": kg_paths_used,
            "kg_expansions": kg_expansions,
            "kg_related_sections": kg_related_sections,
            "retrieval_warnings": retrieval_warnings,
            "retrieval_empty": retrieval_empty,
            "retrieval_empty_reason": retrieval_empty_reason,
            "citation_precision": citation_score.precision,
            "citation_recall": citation_score.recall,
            "citation_f1": citation_score.f1,
            "citation_tp": citation_score.tp,
            "citation_fp": citation_score.fp,
            "citation_fn": citation_score.fn,
            "citation_predicted_sections": citation_score.predicted,
            "citation_ground_truth_sections": citation_score.ground_truth,
            "citation_errors": citation_score.errors,
            "citation_not_scored_due_to_infra": citation_not_scored,
            "citation_proxy_used": proxy_citations_used,
            "missing_ground_truth_in_retrieval": bool(missing_in_retrieval),
            "missing_ground_truth_sections": missing_in_retrieval,
            "multihop": item_multihop,
        }

        trace_pack = _build_trace_pack(
            trace_id=str(trace_id or ""),
            question=str(question or ""),
            answer_text=str(answer or ""),
            label=str(pred_label or ""),
            citations=citations,
            retrieved_docs=retrieved_docs,
            kg_paths_used=kg_paths_used,
            run_provenance=trace_run_provenance,
        )
        trace_require_kg = bool(trace_pack_require_kg_paths and item_multihop)
        trace_issues = validate_trace_pack(
            trace_pack,
            require_kg_paths=trace_require_kg,
            require_run_provenance=True,
        )
        result_entry["provenance_hash"] = trace_pack.get("provenance_hash")
        result_entry["trace_pack_pass"] = len(trace_issues) == 0
        result_entry["trace_pack_issues"] = [issue.to_dict() for issue in trace_issues]
        trace_packs[item_id] = trace_pack
        trace_pack_issues_by_item[item_id] = result_entry["trace_pack_issues"]

        citation_eval = _evaluate_citation_quality(result_entry, reference_sections or None)
        result_entry["citations_ok"] = citation_eval["ok"]
        result_entry["citations_errors"] = citation_eval["errors"]
        for key, val in citation_eval["counts"].items():
            citation_counts[key] = citation_counts.get(key, 0) + int(val)

        results.append(result_entry)
        if item_fallbacks:
            fallback_items.append(
                {
                    "id": item_id,
                    "fallbacks": item_fallbacks,
                }
            )

    num_items = len(results)
    accuracy = correct / answer_total if answer_total else 0.0
    label_accuracy = label_correct / label_total if label_total else 0.0
    unanswerable_accuracy = (
        unanswerable_correct / unanswerable_total if unanswerable_total else 0.0
    )
    grounded_rate = grounded_hits / num_items if num_items else 0.0
    semantic_accuracy = semantic_hits / answer_total if answer_total else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    primary_metric = (
        "label_accuracy"
        if truthiness_items and truthiness_items == label_total
        else "accuracy"
    )

    by_task: Dict[str, Dict[str, float]] = {}
    for task_name, stats in by_task_raw.items():
        count = stats["count"] or 1.0
        by_task[task_name] = {
            "count": int(stats["count"]),
            "accuracy": stats["answer_correct"] / count,
            "label_accuracy": (
                stats["label_correct"] / stats["label_total"]
                if stats["label_total"]
                else 0.0
            ),
            "grounded_rate": stats["grounded_hits"] / count,
        }

    citation_metrics = _finalize_citation_metrics(citation_counts, num_items)
    citation_pr = _aggregate_citation_scores(citation_scores)
    citation_pr["infra_skipped"] = citation_infra_skipped
    citation_pr["proxy_items"] = citation_proxy_items
    status_summary = dict(sorted(status_counts.items()))
    evidence_coverage_recall = (
        total_expected_sections_hit / total_expected_sections if total_expected_sections else 0.0
    )
    multihop_evidence_coverage_recall = (
        multihop_expected_sections_hit / multihop_expected_sections
        if multihop_expected_sections
        else 0.0
    )
    kg_path_usage_rate = (
        multihop_kg_path_used / multihop_items if multihop_items else 0.0
    )
    trace_pack_pass_count = sum(
        1 for result in results if bool(result.get("trace_pack_pass"))
    )
    trace_pack_pass_rate = trace_pack_pass_count / num_items if num_items else 0.0
    multihop_trace_pass_count = sum(
        1
        for result in results
        if bool(result.get("multihop")) and bool(result.get("trace_pack_pass"))
    )
    multihop_trace_pass_rate = (
        multihop_trace_pass_count / multihop_items if multihop_items else 0.0
    )
    fallback_counts_dict = dict(sorted(fallback_counts.items()))
    fallbacks_used = int(sum(fallback_counts.values()))
    fallback_threshold_breached = bool(
        fallback_max_uses is not None and fallbacks_used > int(fallback_max_uses)
    )
    eval_strictness = {
        "schema_validation_required": True,
        "fallback_policy": _fallback_policy(),
        "fallbacks_used": fallbacks_used,
        "fallback_counts": fallback_counts_dict,
        "fallback_items": fallback_items,
        "fallback_max_uses": fallback_max_uses,
        "fallback_threshold_breached": fallback_threshold_breached,
    }

    payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_meta.get("version"),
        "task": dataset_meta.get("task"),
        "slice_definition": _slice_definition(dataset_meta, multihop_only=multihop_only),
        "num_items": num_items,
        "provider": provider,
        "model": model,
        "run_id": run_id,
        "top_k": top_k,
        "ablation": ablation_mode,
        "kg_expansion": kg_expansion_enabled,
        "multihop_only": bool(multihop_only),
        "kg_state_digest": kg_digest,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "answer_score_mode": mode,
        "semantic_threshold": semantic_threshold,
        "primary_metric": primary_metric,
        "accuracy": accuracy,
        "label_accuracy": label_accuracy,
        "unanswerable_accuracy": unanswerable_accuracy,
        "grounded_rate": grounded_rate,
        "semantic_accuracy": semantic_accuracy if semantic else None,
        "avg_latency": avg_latency,
        "by_task": by_task,
        "output_failures": output_failures,
        "output_failure_rate": output_failures / num_items if num_items else 0.0,
        "citation_metrics": citation_metrics,
        "citation_pr": citation_pr,
        "evidence_coverage_recall": evidence_coverage_recall,
        "multihop_metrics": {
            "num_items": multihop_items,
            "evidence_coverage_recall": multihop_evidence_coverage_recall,
            "kg_path_usage_rate": kg_path_usage_rate,
            "trace_pack_pass_rate": multihop_trace_pass_rate,
        },
        "trace_pack_metrics": {
            "num_items": num_items,
            "pass_count": trace_pack_pass_count,
            "pass_rate": trace_pack_pass_rate,
            "multihop_pass_count": multihop_trace_pass_count,
            "multihop_pass_rate": multihop_trace_pass_rate,
            "required_threshold": trace_pack_required_threshold,
            "issues_by_item": trace_pack_issues_by_item,
        },
        "fallbacks_used": fallbacks_used,
        "fallback_counts": fallback_counts_dict,
        "fallback_items": fallback_items,
        "fallback_max_uses": fallback_max_uses,
        "eval_strictness": eval_strictness,
        "status_counts": status_summary,
        "results": results,
    }

    _write_answer_artifacts(
        results,
        dataset_id=dataset_id,
        run_id=run_id,
        base_dir=out_json.parent,
        provider=provider,
        model=model,
        run_meta=run_meta,
    )
    trace_paths = _write_trace_pack_artifacts(
        trace_packs,
        dataset_id=dataset_id,
        run_id=run_id,
        base_dir=out_json.parent,
    )
    for result in results:
        result_id = str(result.get("id") or "")
        path = trace_paths.get(result_id)
        if path is not None:
            result["trace_pack_path"] = str(path)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if emit_hitl_template is not None:
        _write_hitl_templates(
            out_dir=emit_hitl_template,
            dataset_id=dataset_id,
            run_id=run_id,
            results=results,
        )

    lines = [
        "| Accuracy | Label Accuracy | Unanswerable Accuracy | Grounded Rate | Avg Latency (s) |",
        "|---------:|---------------:|----------------------:|--------------:|----------------:|",
        f"| {accuracy:.4f} | {label_accuracy:.4f} | {unanswerable_accuracy:.4f} | {grounded_rate:.4f} | {avg_latency:.4f} |",
        "",
        f"- Dataset: {dataset_id} (task={dataset_meta.get('task')})",
        f"- Provider/model: {provider} / {model}",
        f"- Items: {num_items}, top_k={top_k}",
        f"- Ablation: {ablation_mode or 'none'} (kg_expansion={kg_expansion_enabled})",
        f"- Primary metric: {primary_metric}",
        f"- Answer scoring: {mode}"
        + (f" (threshold={semantic_threshold:.2f})" if mode == "semantic" else ""),
        f"- KG digest: {kg_digest or 'n/a'}",
        f"- Evidence coverage recall: {evidence_coverage_recall:.4f}",
        f"- Multi-hop: count={multihop_items}, evidence_recall={multihop_evidence_coverage_recall:.4f}, "
        f"kg_path_usage={kg_path_usage_rate:.4f}, trace_pack_pass_rate={multihop_trace_pass_rate:.4f}",
        f"- Citations: presence={citation_metrics['presence_rate']:.4f}, "
        f"valid_id={citation_metrics['valid_id_rate']:.4f}, "
        f"supported={citation_metrics['supported_rate']:.4f}, "
        f"overclaim={citation_metrics['overclaim_rate']:.4f}",
        f"- Citation micro: precision={citation_pr['micro']['precision']:.4f}, "
        f"recall={citation_pr['micro']['recall']:.4f}, f1={citation_pr['micro']['f1']:.4f}",
        f"- Eval strictness: fallbacks_used={fallbacks_used}, "
        f"fallback_max_uses={fallback_max_uses if fallback_max_uses is not None else 'disabled'}, "
        f"threshold_breached={fallback_threshold_breached}",
    ]
    if fallback_counts_dict:
        lines.append(
            "- Fallback counts: "
            + ", ".join(f"{k}={v}" for k, v in sorted(fallback_counts_dict.items()))
        )
    if by_task:
        lines.append("")
        lines.append("By-task summary:")
        for task_name, stats in sorted(by_task.items()):
            lines.append(
                f"- {task_name}: accuracy={stats['accuracy']:.4f}, "
                f"label_accuracy={stats['label_accuracy']:.4f}, "
                f"grounded_rate={stats['grounded_rate']:.4f}, "
                f"count={int(stats['count'])}"
            )
    if semantic:
        lines.append("")
        lines.append(
            f"- Semantic accuracy (SequenceMatcher >={semantic_threshold:.2f}): {semantic_accuracy:.4f}"
        )
    out_md.write_text("\n".join(lines), encoding="utf-8")

    missing_provenance = [str(result.get("id") or "") for result in results if not result.get("provenance_hash")]
    if missing_provenance:
        raise RuntimeError(
            "Trace-pack validation failed: provenance_hash missing for item(s): "
            + ", ".join(sorted(missing_provenance))
        )
    if trace_pack_required_threshold is not None and multihop_trace_pass_rate < trace_pack_required_threshold:
        raise RuntimeError(
            "Trace-pack validation failed: multihop trace_pack_pass_rate "
            f"{multihop_trace_pass_rate:.4f} < required threshold {trace_pack_required_threshold:.4f}"
        )
    if fallback_threshold_breached:
        raise RuntimeError(
            "Eval strictness failed: fallbacks_used "
            f"{fallbacks_used} > fallback_max_uses {fallback_max_uses}. "
            f"Counts: {fallback_counts_dict}"
        )
    return out_json, out_md


def _load_eval_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ablation_metrics(payload: Mapping[str, object]) -> dict[str, float]:
    citation_metrics = payload.get("citation_metrics") or {}
    multihop = payload.get("multihop_metrics") or {}
    return {
        "accuracy": float(payload.get("accuracy") or 0.0),
        "label_accuracy": float(payload.get("label_accuracy") or 0.0),
        "grounded_rate": float(payload.get("grounded_rate") or 0.0),
        "citation_supported_rate": float(citation_metrics.get("supported_rate") or 0.0),
        "evidence_coverage_recall": float(payload.get("evidence_coverage_recall") or 0.0),
        "multihop_evidence_coverage_recall": float(
            multihop.get("evidence_coverage_recall") or 0.0
        ),
        "kg_path_usage_rate": float(multihop.get("kg_path_usage_rate") or 0.0),
        "trace_pack_pass_rate": float(multihop.get("trace_pack_pass_rate") or 0.0),
        "fallbacks_used": float(payload.get("fallbacks_used") or 0.0),
    }


def _build_ablation_summary(
    *,
    dataset_id: str,
    slice_definition: Mapping[str, object],
    run_id: str,
    manifest_path: Path,
    provider: str,
    model: str,
    top_k: int,
    condition_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    condition_metrics = {
        name: _ablation_metrics(payload) for name, payload in condition_payloads.items()
    }
    baseline = condition_metrics.get("faiss_only", {})
    candidate = condition_metrics.get("faiss_plus_kg", {})
    metric_names = sorted(set(baseline.keys()) | set(candidate.keys()))
    deltas: dict[str, float] = {}
    comparison_table: list[dict[str, object]] = []
    for metric in metric_names:
        a = float(baseline.get(metric) or 0.0)
        b = float(candidate.get(metric) or 0.0)
        delta = b - a
        deltas[metric] = delta
        comparison_table.append(
            {"metric": metric, "faiss_only": a, "faiss_plus_kg": b, "delta": delta}
        )

    n = int((condition_payloads.get("faiss_plus_kg") or {}).get("num_items") or 0)
    confidence_caveat = (
        f"small_sample_warning: N={n}; treat deltas as directional"
        if n < 30
        else None
    )
    return {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "slice_definition": dict(slice_definition),
        "conditions": condition_metrics,
        "deltas": deltas,
        "comparison_table": comparison_table,
        "confidence_caveat": confidence_caveat,
        "run_configuration": {
            "manifest_path": str(manifest_path),
            "top_k": top_k,
            "provider": provider,
            "model": model,
            "faiss_index": str(Path("data") / "faiss" / "index.faiss"),
            "faiss_model": "all-MiniLM-L12-v2",
            "kg_expansion_provider": "fuseki|json_stub (from runtime env)",
        },
        "artifacts": {
            name: {
                "eval_json": str((condition_payloads[name]).get("artifact_json") or ""),
                "eval_md": str((condition_payloads[name]).get("artifact_md") or ""),
            }
            for name in sorted(condition_payloads.keys())
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate eval/* datasets using the RAG pipeline + remote LLMs."
    )
    parser.add_argument(
        "--dataset-id",
        required=True,
        help="Dataset ID from eval/manifest.json (e.g., ear_compliance.v1).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval") / "manifest.json",
        help="Path to eval manifest JSON.",
    )
    parser.add_argument(
        "--llm-provider",
        choices=["nvidia_nim", "groq"],
        default=None,
        help="LLM provider override (defaults to secrets config).",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model override (useful if a default model is decommissioned).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of contexts to retrieve before generation.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Optional cap on number of items to evaluate.",
    )
    parser.add_argument(
        "--answer-score-mode",
        choices=list(_ANSWER_SCORE_MODES),
        default="semantic",
        help="How to score answer correctness for `accuracy` (default: semantic).",
    )
    parser.add_argument(
        "--semantic-threshold",
        type=float,
        default=0.6,
        help="Threshold for semantic matching (SequenceMatcher ratio).",
    )
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Include a semantic accuracy signal (SequenceMatcher >= threshold).",
    )
    parser.add_argument(
        "--ablation",
        choices=list(_ABLATION_MODES),
        default=None,
        help="Retrieval ablation mode: faiss_only or faiss_plus_kg.",
    )
    parser.add_argument(
        "--kg-expansion",
        choices=[0, 1],
        type=int,
        default=None,
        help="Explicit KG expansion toggle (0/1). Keep unset to follow --ablation/default behavior.",
    )
    parser.add_argument(
        "--multihop-only",
        action="store_true",
        help="Evaluate only items that satisfy the multi-hop selector.",
    )
    parser.add_argument(
        "--emit-hitl-template",
        type=Path,
        default=None,
        help="Write HITL decision templates per item under this output directory.",
    )
    parser.add_argument(
        "--ablation-compare",
        action="store_true",
        help="Run both ablations and write a combined comparison summary.",
    )
    parser.add_argument(
        "--ablation-run-id",
        default=None,
        help="Run id for dist/ablations/<run_id>/ outputs when --ablation-compare is used.",
    )
    parser.add_argument(
        "--trace-pack-threshold",
        type=float,
        default=None,
        help="Required minimum trace_pack_pass_rate on multihop items (used for faiss_plus_kg).",
    )
    parser.add_argument(
        "--fallback-max-uses",
        type=int,
        default=_DEFAULT_FALLBACK_MAX_USES,
        help=(
            "Maximum allowed fallback normalizations/inference events before failing the run. "
            "Use -1 to disable."
        ),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Where to write metrics JSON (defaults to dist/eval/<dataset>.rag.<provider>.json).",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=None,
        help="Where to write markdown summary (defaults to dist/eval/<dataset>.rag.<provider>.md).",
    )
    args = parser.parse_args(argv)
    fallback_max_uses = None if args.fallback_max_uses < 0 else args.fallback_max_uses

    try:
        ensure_valid_datasets(
            manifest_path=args.manifest,
            schema_path=Path("eval") / "schema.json",
            dataset_ids=[args.dataset_id],
        )
    except Exception as exc:
        print(f"Failed: {exc}")
        return 1

    cfg = get_llm_config(
        provider_override=args.llm_provider, model_override=args.llm_model
    )
    provider = cfg.provider.provider
    model = cfg.provider.model
    safe_model = _safe_name(model or "default")
    suffix = f".{args.ablation}" if args.ablation else ""
    default_json = Path("dist") / "eval" / f"{args.dataset_id}.rag.{provider}.{safe_model}{suffix}.json"
    default_md = Path("dist") / "eval" / f"{args.dataset_id}.rag.{provider}.{safe_model}{suffix}.md"
    out_json = args.out_json or default_json
    out_md = args.out_md or default_md
    kg_expansion_flag = None if args.kg_expansion is None else bool(args.kg_expansion)
    if args.ablation == "faiss_only" and kg_expansion_flag is True:
        print("Failed: --ablation faiss_only conflicts with --kg-expansion 1")
        return 1
    if args.ablation == "faiss_plus_kg" and kg_expansion_flag is False:
        print("Failed: --ablation faiss_plus_kg conflicts with --kg-expansion 0")
        return 1
    default_trace_threshold = (
        0.9 if args.ablation == "faiss_plus_kg" and (args.multihop_only or "multihop" in args.dataset_id.lower()) else None
    )
    trace_threshold = args.trace_pack_threshold if args.trace_pack_threshold is not None else default_trace_threshold

    if args.ablation_compare:
        run_id = _safe_name(args.ablation_run_id or f"{args.dataset_id}.ablation")
        root = Path("dist") / "ablations" / run_id
        condition_payloads: dict[str, dict[str, object]] = {}
        try:
            for cond in _ABLATION_MODES:
                cond_json = root / "conditions" / f"{args.dataset_id}.{cond}.json"
                cond_md = root / "conditions" / f"{args.dataset_id}.{cond}.md"
                cond_threshold = (
                    args.trace_pack_threshold
                    if args.trace_pack_threshold is not None
                    else (0.9 if cond == "faiss_plus_kg" else None)
                )
                j, m = evaluate_dataset(
                    args.dataset_id,
                    manifest_path=args.manifest,
                    llm_provider=args.llm_provider,
                    llm_model=args.llm_model,
                    top_k=args.top_k,
                    max_items=args.max_items,
                    out_json=cond_json,
                    out_md=cond_md,
                    answer_score_mode=args.answer_score_mode,
                    semantic_threshold=args.semantic_threshold,
                    semantic=args.semantic,
                    ablation=cond,
                    kg_expansion=(cond == "faiss_plus_kg"),
                    multihop_only=args.multihop_only,
                    emit_hitl_template=args.emit_hitl_template,
                    trace_pack_require_kg_paths=(cond == "faiss_plus_kg"),
                    trace_pack_required_threshold=cond_threshold,
                    fallback_max_uses=fallback_max_uses,
                )
                payload = _load_eval_payload(j)
                payload["artifact_json"] = str(j)
                payload["artifact_md"] = str(m)
                condition_payloads[cond] = payload
            slice_definition = (
                condition_payloads.get("faiss_plus_kg", {}).get("slice_definition")
                or condition_payloads.get("faiss_only", {}).get("slice_definition")
                or {}
            )
            summary = _build_ablation_summary(
                dataset_id=args.dataset_id,
                slice_definition=slice_definition if isinstance(slice_definition, Mapping) else {},
                run_id=run_id,
                manifest_path=args.manifest,
                provider=provider,
                model=model,
                top_k=args.top_k,
                condition_payloads=condition_payloads,
            )
            summary_path = root / "ablation_summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            print(f"Failed: {exc}")
            return 1
        print(f"Wrote {summary_path}")
        return 0

    try:
        j, m = evaluate_dataset(
            args.dataset_id,
            manifest_path=args.manifest,
            llm_provider=args.llm_provider,
            llm_model=args.llm_model,
            top_k=args.top_k,
            max_items=args.max_items,
            out_json=out_json,
            out_md=out_md,
            answer_score_mode=args.answer_score_mode,
            semantic_threshold=args.semantic_threshold,
            semantic=args.semantic,
            ablation=args.ablation,
            kg_expansion=kg_expansion_flag,
            multihop_only=args.multihop_only,
            emit_hitl_template=args.emit_hitl_template,
            trace_pack_require_kg_paths=args.ablation == "faiss_plus_kg",
            trace_pack_required_threshold=trace_threshold,
            fallback_max_uses=fallback_max_uses,
        )
    except Exception as exc:  # pragma: no cover - surfaced as CLI failure
        print(f"Failed: {exc}")
        return 1
    print(f"Wrote {j} and {m}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
