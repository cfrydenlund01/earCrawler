from __future__ import annotations

"""Dataset-driven evaluation using the RAG pipeline + remote LLM providers."""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from collections import Counter

from api_clients.llm_client import LLMProviderError
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
    run_id = _safe_name(out_json.stem)
    run_meta = {
        "dataset_version": dataset_meta.get("version"),
        "kg_state_digest": kg_digest,
        "manifest_path": str(manifest_path),
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

    by_task_raw: Dict[str, Dict[str, float]] = {}

    mode = (answer_score_mode or "").strip().lower() or "semantic"
    if mode not in _ANSWER_SCORE_MODES:
        raise ValueError(f"Unsupported --answer-score-mode: {mode}")
    if semantic_threshold <= 0 or semantic_threshold > 1:
        raise ValueError("semantic_threshold must be in (0, 1]")

    for idx, item in enumerate(_iter_items(data_path)):
        if max_items is not None and idx >= max_items:
            break
        question = item.get("question", "")
        ground_truth = item.get("ground_truth", {}) or {}
        gt_answer = (ground_truth.get("answer_text") or "").strip()
        gt_label = (ground_truth.get("label") or "").strip().lower()
        task = str(item.get("task", "") or "").strip()
        ear_sections = item.get("ear_sections") or []

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
        citations: list[dict] | None = None
        evidence_okay: dict | None = None
        assumptions: list[str] | None = None
        citation_span_ids: list[str] | None = None
        trace_id: str | None = None

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
                strict_retrieval=False,
                strict_output=True,
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
            trace_id = rag_result.get("trace_id")
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
        pred_sections = extract_predicted_sections(
            {"citations": citations, "used_sections": used_sections}
        )
        proxy_citations_used = bool(not (citations or []) and bool(pred_sections))
        if proxy_citations_used:
            citation_proxy_items += 1

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
        if proxy_citations_used:
            citation_errors.append({"code": "proxy_citations_used"})
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

        result_entry = {
            "id": item.get("id"),
            "question": question,
            "task": task,
            "ground_truth_answer": gt_answer,
            "ground_truth_label": gt_label,
            "pred_answer": answer,
            "answer_text": answer,
            "pred_label_raw": pred_label_raw,
            "pred_label": pred_label,
            "pred_label_normalization": label_norm,
            "grounded": grounded,
            "expected_sections": ear_sections,
            "used_sections": used_sections,
            "retrieved_docs": retrieved_docs,
            "trace_id": trace_id,
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
        }

        citation_eval = _evaluate_citation_quality(result_entry, reference_sections or None)
        result_entry["citations_ok"] = citation_eval["ok"]
        result_entry["citations_errors"] = citation_eval["errors"]
        for key, val in citation_eval["counts"].items():
            citation_counts[key] = citation_counts.get(key, 0) + int(val)

        results.append(result_entry)

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

    payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_meta.get("version"),
        "task": dataset_meta.get("task"),
        "num_items": num_items,
        "provider": provider,
        "model": model,
        "run_id": run_id,
        "top_k": top_k,
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

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "| Accuracy | Label Accuracy | Unanswerable Accuracy | Grounded Rate | Avg Latency (s) |",
        "|---------:|---------------:|----------------------:|--------------:|----------------:|",
        f"| {accuracy:.4f} | {label_accuracy:.4f} | {unanswerable_accuracy:.4f} | {grounded_rate:.4f} | {avg_latency:.4f} |",
        "",
        f"- Dataset: {dataset_id} (task={dataset_meta.get('task')})",
        f"- Provider/model: {provider} / {model}",
        f"- Items: {num_items}, top_k={top_k}",
        f"- Primary metric: {primary_metric}",
        f"- Answer scoring: {mode}"
        + (f" (threshold={semantic_threshold:.2f})" if mode == "semantic" else ""),
        f"- KG digest: {kg_digest or 'n/a'}",
        f"- Citations: presence={citation_metrics['presence_rate']:.4f}, "
        f"valid_id={citation_metrics['valid_id_rate']:.4f}, "
        f"supported={citation_metrics['supported_rate']:.4f}, "
        f"overclaim={citation_metrics['overclaim_rate']:.4f}",
        f"- Citation micro: precision={citation_pr['micro']['precision']:.4f}, "
        f"recall={citation_pr['micro']['recall']:.4f}, f1={citation_pr['micro']['f1']:.4f}",
    ]
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
    return out_json, out_md


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

    cfg = get_llm_config(
        provider_override=args.llm_provider, model_override=args.llm_model
    )
    provider = cfg.provider.provider
    model = cfg.provider.model
    safe_model = _safe_name(model or "default")
    default_json = Path("dist") / "eval" / f"{args.dataset_id}.rag.{provider}.{safe_model}.json"
    default_md = Path("dist") / "eval" / f"{args.dataset_id}.rag.{provider}.{safe_model}.md"
    out_json = args.out_json or default_json
    out_md = args.out_md or default_md

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
        )
    except Exception as exc:  # pragma: no cover - surfaced as CLI failure
        print(f"Failed: {exc}")
        return 1
    print(f"Wrote {j} and {m}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
