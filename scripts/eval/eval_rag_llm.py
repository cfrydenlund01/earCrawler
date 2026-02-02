from __future__ import annotations

"""Dataset-driven evaluation using the RAG pipeline + remote LLM providers."""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from api_clients.llm_client import LLMProviderError
from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.eval.label_inference import infer_label
from earCrawler.rag.output_schema import DEFAULT_ALLOWED_LABELS
from earCrawler.rag.pipeline import answer_with_rag

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
    kg_digest = (manifest.get("kg_state", {}) or {}).get("digest")
    dataset_meta, data_path = _resolve_dataset(manifest, dataset_id, manifest_path)

    cfg = get_llm_config(provider_override=llm_provider, model_override=llm_model)
    if not cfg.enable_remote:
        raise RuntimeError(
            "Remote LLMs are disabled. Set EARCRAWLER_ENABLE_REMOTE_LLM=1 and configure provider keys."
        )
    provider = cfg.provider.provider
    model = cfg.provider.model

    results: List[Dict[str, Any]] = []
    latencies: List[float] = []

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
        error: str | None = None
        retrieval_warnings: list[dict[str, object]] = []
        retrieval_empty = False
        retrieval_empty_reason: str | None = None
        output_ok = True
        output_error: dict | None = None
        raw_answer: str | None = None
        status = "ok"
        citations: list[dict] | None = None
        evidence_okay: dict | None = None
        assumptions: list[str] | None = None
        citation_span_ids: list[str] | None = None

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
            retrieval_warnings = list(rag_result.get("retrieval_warnings") or [])
            retrieval_empty = bool(rag_result.get("retrieval_empty"))
            retrieval_empty_reason = rag_result.get("retrieval_empty_reason")
            citations = rag_result.get("citations")
            evidence_okay = rag_result.get("evidence_okay")
            assumptions = rag_result.get("assumptions")
            citation_span_ids = rag_result.get("citation_span_ids")
            # Prefer structured label from the JSON contract when present.
            justification = (rag_result.get("justification") or "").strip() or None
            if not output_ok:
                status = "failed_output_schema"
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
        except Exception as exc:  # pragma: no cover - defensive
            error = f"unexpected_error: {exc}"
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
        if gt_answer:
            answer_total += 1
            if answer_correct:
                correct += 1

        if semantic and gt_answer and answer:
            if _semantic_match_ratio(answer, gt_answer) >= semantic_threshold:
                semantic_hits += 1

        if gt_label:
            label_total += 1
            if pred_label == gt_label:
                label_correct += 1
            if gt_label in {"true", "false"}:
                truthiness_items += 1
        if gt_label == "unanswerable":
            unanswerable_total += 1
            if pred_label == "unanswerable":
                unanswerable_correct += 1

        if task:
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

        results.append(
            {
                "id": item.get("id"),
                "question": question,
                "task": task,
                "ground_truth_answer": gt_answer,
                "ground_truth_label": gt_label,
                "pred_answer": answer,
                "pred_label_raw": pred_label_raw,
                "pred_label": pred_label,
                "pred_label_normalization": label_norm,
                "grounded": grounded,
                "expected_sections": ear_sections,
                "used_sections": used_sections,
                "evidence": item.get("evidence"),
                "error": error,
                "status": status,
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

    payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_meta.get("version"),
        "task": dataset_meta.get("task"),
        "num_items": num_items,
        "provider": provider,
        "model": model,
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
        "results": results,
    }

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
