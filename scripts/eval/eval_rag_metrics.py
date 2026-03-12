from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from earCrawler.eval.citation_metrics import CitationScore
from earCrawler.eval.groundedness_gates import (
    evaluate_groundedness_signals,
    finalize_groundedness_metrics,
)


def evaluate_citation_quality(
    result: Mapping[str, object], reference_sections: set[str] | None
) -> dict[str, object]:
    return evaluate_groundedness_signals(result, reference_sections=reference_sections)


def finalize_citation_metrics(
    counts: Mapping[str, int], num_items: int
) -> dict[str, object]:
    return finalize_groundedness_metrics(counts, num_items)


def aggregate_citation_scores(scores: Sequence[CitationScore]) -> dict[str, object]:
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
    for score in scores:
        for err in score.errors:
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


def ablation_metrics(payload: Mapping[str, object]) -> dict[str, float]:
    citation_metrics = payload.get("citation_metrics") or {}
    citation_pr = payload.get("citation_pr") or {}
    citation_micro = citation_pr.get("micro") if isinstance(citation_pr, Mapping) else {}
    citation_macro = citation_pr.get("macro") if isinstance(citation_pr, Mapping) else {}
    multihop = payload.get("multihop_metrics") or {}
    return {
        "accuracy": float(payload.get("accuracy") or 0.0),
        "label_accuracy": float(payload.get("label_accuracy") or 0.0),
        "grounded_rate": float(payload.get("grounded_rate") or 0.0),
        "citation_supported_rate": float(citation_metrics.get("supported_rate") or 0.0),
        "citation_micro_precision": float((citation_micro or {}).get("precision") or 0.0),
        "citation_micro_recall": float((citation_micro or {}).get("recall") or 0.0),
        "citation_micro_f1": float((citation_micro or {}).get("f1") or 0.0),
        "citation_macro_precision": float((citation_macro or {}).get("precision") or 0.0),
        "citation_macro_recall": float((citation_macro or {}).get("recall") or 0.0),
        "citation_macro_f1": float((citation_macro or {}).get("f1") or 0.0),
        "evidence_coverage_recall": float(payload.get("evidence_coverage_recall") or 0.0),
        "multihop_evidence_coverage_recall": float(multihop.get("evidence_coverage_recall") or 0.0),
        "kg_path_usage_rate": float(multihop.get("kg_path_usage_rate") or 0.0),
        "trace_pack_pass_rate": float(multihop.get("trace_pack_pass_rate") or 0.0),
        "fallbacks_used": float(payload.get("fallbacks_used") or 0.0),
    }


def build_ablation_summary(
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
        name: ablation_metrics(payload) for name, payload in condition_payloads.items()
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
                "provenance_json": str((condition_payloads[name]).get("provenance_path") or ""),
            }
            for name in sorted(condition_payloads.keys())
        },
    }


def build_retrieval_compare_summary(
    *,
    dataset_id: str,
    slice_definition: Mapping[str, object],
    run_id: str,
    manifest_path: Path,
    provider: str,
    model: str,
    top_k: int,
    ablation: str | None,
    kg_expansion: bool | None,
    condition_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    condition_metrics = {
        name: ablation_metrics(payload) for name, payload in condition_payloads.items()
    }
    baseline = condition_metrics.get("dense", {})
    candidate = condition_metrics.get("hybrid", {})
    metric_names = sorted(set(baseline.keys()) | set(candidate.keys()))
    deltas: dict[str, float] = {}
    comparison_table: list[dict[str, object]] = []
    for metric in metric_names:
        dense_value = float(baseline.get(metric) or 0.0)
        hybrid_value = float(candidate.get(metric) or 0.0)
        delta = hybrid_value - dense_value
        deltas[metric] = delta
        comparison_table.append(
            {
                "metric": metric,
                "dense": dense_value,
                "hybrid": hybrid_value,
                "delta": delta,
            }
        )

    n = int((condition_payloads.get("hybrid") or {}).get("num_items") or 0)
    confidence_caveat = (
        f"small_sample_warning: N={n}; treat deltas as directional"
        if n < 30
        else None
    )
    return {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "comparison_dimension": "retrieval_mode",
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
            "ablation": ablation,
            "kg_expansion": kg_expansion,
        },
        "artifacts": {
            name: {
                "eval_json": str((condition_payloads[name]).get("artifact_json") or ""),
                "eval_md": str((condition_payloads[name]).get("artifact_md") or ""),
                "provenance_json": str((condition_payloads[name]).get("provenance_path") or ""),
            }
            for name in sorted(condition_payloads.keys())
        },
    }

