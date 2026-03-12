from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_rag_evaluations(
    *,
    manifest: Path,
    dataset_id: str | None,
    provider: str,
    model: str,
    top_k: int,
    retrieval_mode: str | None,
    compare_retrieval_modes: bool,
    max_items: int | None,
    answer_score_mode: str,
    semantic_threshold: float,
    semantic: bool,
    fallback_threshold: int | None,
    out_dir: Path,
) -> list[str]:
    from eval.validate_datasets import ensure_valid_datasets
    from scripts.eval import eval_rag_llm

    manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    dataset_entries = manifest_obj.get("datasets", []) or []
    if dataset_id:
        dataset_entries = [
            entry for entry in dataset_entries if entry.get("id") == dataset_id
        ]
        if not dataset_entries:
            raise ValueError(f"Dataset not found: {dataset_id}")
        dataset_ids: list[str] | None = [dataset_id]
    else:
        dataset_ids = None

    ensure_valid_datasets(
        manifest_path=manifest,
        schema_path=Path("eval") / "schema.json",
        dataset_ids=dataset_ids,
    )

    messages: list[str] = []
    for entry in dataset_entries:
        ds_id = entry.get("id")
        safe_model = eval_rag_llm._safe_name(model or "default")
        suffix = f".{retrieval_mode}" if retrieval_mode else ""
        out_json = Path(out_dir) / f"{ds_id}.rag.{provider}.{safe_model}{suffix}.json"
        out_md = Path(out_dir) / f"{ds_id}.rag.{provider}.{safe_model}{suffix}.md"
        if compare_retrieval_modes:
            summary_path = eval_rag_llm.compare_retrieval_modes(
                ds_id,
                manifest_path=manifest,
                llm_provider=provider,
                llm_model=model,
                top_k=top_k,
                max_items=max_items,
                answer_score_mode=answer_score_mode,
                semantic_threshold=semantic_threshold,
                semantic=semantic,
                ablation=None,
                kg_expansion=None,
                multihop_only=False,
                emit_hitl_template=None,
                trace_pack_required_threshold=None,
                fallback_max_uses=fallback_threshold,
                out_root=Path(out_dir) / "retrieval_compare",
                run_id=eval_rag_llm._safe_name(f"{ds_id}.retrieval"),
            )
            messages.append(f"{ds_id}: wrote {summary_path}")
            continue

        eval_rag_llm.evaluate_dataset(
            ds_id,
            manifest_path=manifest,
            llm_provider=provider,
            llm_model=model,
            top_k=top_k,
            retrieval_mode=retrieval_mode,
            max_items=max_items,
            out_json=out_json,
            out_md=out_md,
            answer_score_mode=answer_score_mode,
            semantic_threshold=semantic_threshold,
            semantic=semantic,
            fallback_max_uses=fallback_threshold,
        )
        messages.append(f"{ds_id}: wrote {out_json}")
    return messages


def compute_fr_coverage(
    *,
    manifest: Path,
    corpus: Path,
    dataset_id: str,
    only_v2: bool,
    dataset_id_pattern: str | None,
    retrieval_k: int,
    retrieval_mode: str | None,
    max_items: int | None,
    top_missing_sections: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from eval.validate_datasets import ensure_valid_datasets
    from earCrawler.eval.coverage_checks import (
        build_fr_coverage_report,
        build_fr_coverage_summary,
    )

    selected_dataset_ids: list[str] | None = None
    if dataset_id and dataset_id != "all":
        selected_dataset_ids = [dataset_id]
    ensure_valid_datasets(
        manifest_path=manifest,
        schema_path=Path("eval") / "schema.json",
        dataset_ids=selected_dataset_ids,
    )
    report = build_fr_coverage_report(
        manifest=manifest,
        corpus=corpus,
        dataset_id=dataset_id,
        only_v2=only_v2,
        dataset_id_pattern=dataset_id_pattern,
        retrieval_k=retrieval_k,
        retrieval_mode=retrieval_mode,
        max_items=max_items,
        top_missing_sections=top_missing_sections,
    )
    summary_obj = build_fr_coverage_summary(
        report, top_missing_sections=top_missing_sections
    )
    return report, summary_obj


def failure_coverage_artifacts(
    *,
    manifest: Path,
    corpus: Path,
    dataset_id: str,
    only_v2: bool,
    dataset_id_pattern: str | None,
    retrieval_k: int,
    error: Exception,
) -> tuple[dict[str, Any], dict[str, Any]]:
    message = str(error)
    failure_report = {
        "manifest_path": str(manifest),
        "corpus_path": str(corpus),
        "dataset_selector": {
            "dataset_id": dataset_id,
            "only_v2": bool(only_v2),
            "dataset_id_pattern": dataset_id_pattern,
        },
        "retrieval_k": retrieval_k,
        "error": message,
    }
    failure_summary = {
        "manifest_path": str(manifest),
        "corpus_path": str(corpus),
        "dataset_selector": failure_report["dataset_selector"],
        "retrieval_k": retrieval_k,
        "error": message,
        "datasets": [],
        "summary": {},
    }
    return failure_report, failure_summary


def build_fr_coverage_summary_lines(
    summary_obj: dict[str, Any], *, top_missing_sections: int
) -> list[str]:
    lines: list[str] = [
        "dataset_id | items | expected | missing_retrieval | missing_rate | missing_corpus",
        "-" * 88,
    ]
    ds_rows = summary_obj.get("datasets") or []
    for row in ds_rows:
        ds_id = str(row.get("dataset_id") or "")
        items = int(row.get("num_items") or 0)
        expected = int(row.get("expected_sections") or 0)
        miss_r = int(row.get("num_missing_in_retrieval") or 0)
        miss_c = int(row.get("num_missing_in_corpus") or 0)
        try:
            rate = float(row.get("missing_in_retrieval_rate") or 0.0)
        except Exception:
            rate = 0.0
        lines.append(f"{ds_id} | {items} | {expected} | {miss_r} | {rate:.4f} | {miss_c}")

    summary = summary_obj.get("summary") or {}
    missing_in_corpus = int(summary.get("num_missing_in_corpus") or 0)
    missing_in_retrieval = int(summary.get("num_missing_in_retrieval") or 0)
    worst_ds = summary.get("worst_dataset_id") or "n/a"
    try:
        worst_rate = float(summary.get("worst_missing_in_retrieval_rate") or 0.0)
    except Exception:
        worst_rate = 0.0
    lines.append(
        f"overall: missing_in_corpus={missing_in_corpus}, missing_in_retrieval={missing_in_retrieval}, "
        f"worst_dataset={worst_ds} worst_missing_rate={worst_rate:.4f}"
    )
    top_missing = summary.get("top_missing_sections") or []
    if top_missing:
        lines.append("top_missing_sections:")
        for row in top_missing[:top_missing_sections]:
            if isinstance(row, dict):
                lines.append(f"  - {row.get('section_id')}: {row.get('count')}")
    return lines

