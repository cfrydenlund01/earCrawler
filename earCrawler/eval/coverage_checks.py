from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Callable, Iterable, Mapping, Sequence

from earCrawler.eval.evidence_resolver import load_corpus_index
from earCrawler.rag.pipeline import _normalize_section_id


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)


def _resolve_dataset_path(
    manifest_path: Path, dataset_entry: Mapping[str, object]
) -> Path:
    raw_file = dataset_entry.get("file")
    if not raw_file:
        raise ValueError(f"Dataset entry missing file: {dataset_entry.get('id')}")
    data_file = Path(str(raw_file))
    if not data_file.is_absolute() and not data_file.exists():
        data_file = manifest_path.parent / data_file
    return data_file


def _expected_sections_for_item(item: Mapping[str, object]) -> list[str]:
    expected: set[str] = set()

    sections_raw: Sequence[object] = item.get("ear_sections") or []
    for sec in sections_raw:
        norm = _normalize_section_id(sec)
        if norm:
            expected.add(norm)

    evidence = item.get("evidence") or {}
    doc_spans: Sequence[Mapping[str, object]] = evidence.get("doc_spans") or []
    for span in doc_spans:
        norm = _normalize_section_id(span.get("span_id"))
        if norm:
            expected.add(norm)

    return sorted(expected)


def build_ecfr_coverage_report(
    *,
    manifest: Path,
    corpus: Path,
    dataset_id: str = "all",
    retrieval_k: int = 10,
    max_items: int | None = None,
    retrieve_context: (
        Callable[[str, int], Sequence[Mapping[str, object]]] | None
    ) = None,
) -> dict[str, object]:
    """Build a report that checks section coverage + FAISS retrievability.

    Intended behavior
    - Enumerate expected EAR sections from each dataset item (ear_sections + evidence.doc_spans).
    - Verify each expected section exists in the corpus JSONL.
    - Query the FAISS retriever with the question and record the rank (1-based) of each expected section.
    """

    manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    dataset_entries = manifest_obj.get("datasets", []) or []
    if dataset_id != "all":
        dataset_entries = [
            entry for entry in dataset_entries if entry.get("id") == dataset_id
        ]
        if not dataset_entries:
            raise ValueError(f"Dataset not found: {dataset_id}")

    corpus_index = load_corpus_index(corpus)

    if retrieve_context is None:
        from earCrawler.rag.pipeline import (
            _ensure_retriever,
            retrieve_regulation_context,
        )

        if _ensure_retriever() is None:
            raise RuntimeError(
                "FAISS retriever unavailable (missing optional deps or index/model not configured)."
            )

        def retrieve_context(question: str, k: int) -> Sequence[Mapping[str, object]]:
            return retrieve_regulation_context(question, top_k=k)

    report: dict[str, object] = {
        "manifest_path": str(manifest),
        "corpus_path": str(corpus),
        "dataset_id": dataset_id,
        "retrieval_k": retrieval_k,
        "datasets": [],
    }

    total_expected = 0
    total_missing_in_corpus = 0
    total_missing_in_retrieval = 0
    hit_ranks: list[int] = []

    for entry in dataset_entries:
        ds_id = str(entry.get("id") or "")
        data_file = _resolve_dataset_path(manifest, entry)
        if not data_file.exists():
            raise ValueError(f"Dataset not found: {data_file}")

        item_reports: list[dict[str, object]] = []
        ds_expected = 0
        ds_missing_in_corpus = 0
        ds_missing_in_retrieval = 0
        ds_rank_hits: list[int] = []

        for idx, item in enumerate(_iter_jsonl(data_file)):
            if max_items is not None and idx >= max_items:
                break
            question = str(item.get("question") or "")
            expected_sections = _expected_sections_for_item(item)
            missing_in_corpus = [
                sec for sec in expected_sections if sec not in corpus_index
            ]

            retrieved = list(retrieve_context(question, retrieval_k))
            retrieved_sections: list[str] = []
            for rec in retrieved:
                sec = rec.get("section_id") if isinstance(rec, Mapping) else None
                norm = _normalize_section_id(sec)
                if norm:
                    retrieved_sections.append(norm)

            ranks: dict[str, int | None] = {sec: None for sec in expected_sections}
            for rank, sec in enumerate(retrieved_sections, start=1):
                if sec in ranks and ranks[sec] is None:
                    ranks[sec] = rank

            missing_in_retrieval = [sec for sec, rank in ranks.items() if rank is None]
            rank_values = [rank for rank in ranks.values() if isinstance(rank, int)]

            ds_expected += len(expected_sections)
            ds_missing_in_corpus += len(missing_in_corpus)
            ds_missing_in_retrieval += len(missing_in_retrieval)
            ds_rank_hits.extend(rank_values)

            item_reports.append(
                {
                    "item_id": item.get("id"),
                    "expected_sections": expected_sections,
                    "missing_in_corpus": missing_in_corpus,
                    "retrieval": {
                        "k": retrieval_k,
                        "ranks": ranks,
                        "missing": missing_in_retrieval,
                        "retrieved_sections": retrieved_sections,
                    },
                }
            )

        dataset_report = {
            "dataset_id": ds_id,
            "file": str(data_file),
            "items": item_reports,
            "summary": {
                "expected_sections": ds_expected,
                "missing_in_corpus": ds_missing_in_corpus,
                "missing_in_retrieval": ds_missing_in_retrieval,
                "median_retrieval_rank": (
                    median(ds_rank_hits) if ds_rank_hits else None
                ),
            },
        }
        report["datasets"].append(dataset_report)

        total_expected += ds_expected
        total_missing_in_corpus += ds_missing_in_corpus
        total_missing_in_retrieval += ds_missing_in_retrieval
        hit_ranks.extend(ds_rank_hits)

    report["summary"] = {
        "expected_sections": total_expected,
        "missing_in_corpus": total_missing_in_corpus,
        "missing_in_retrieval": total_missing_in_retrieval,
        "median_retrieval_rank": (median(hit_ranks) if hit_ranks else None),
    }
    return report


def build_fr_coverage_report(*args, **kwargs) -> dict[str, object]:
    """Backwards-compatible alias; prefer build_ecfr_coverage_report()."""

    return build_ecfr_coverage_report(*args, **kwargs)


def build_grounding_contract_report(
    *,
    eval_json: Path,
    min_grounded_rate: float = 1.0,
    min_expected_hit_rate: float = 1.0,
) -> dict[str, object]:
    """Validate that label correctness implies grounded retrieval.

    Contract per item:
    - `pred_label` matches `ground_truth_label`
    - AND `used_sections` includes all `expected_sections`
    """

    payload = json.loads(eval_json.read_text(encoding="utf-8"))
    results: Sequence[Mapping[str, object]] = payload.get("results") or []

    label_total = 0
    label_correct = 0
    expected_total = 0
    expected_hit_any = 0
    expected_hit_all = 0
    contract_total = 0
    contract_pass = 0
    failures: list[dict[str, object]] = []

    for res in results:
        gt_label = str(res.get("ground_truth_label") or "").strip().lower()
        pred_label = str(res.get("pred_label") or "").strip().lower()
        expected_sections = [str(s) for s in (res.get("expected_sections") or []) if s]
        used_sections = [str(s) for s in (res.get("used_sections") or []) if s]

        label_ok = False
        if gt_label:
            label_total += 1
            label_ok = pred_label == gt_label
            if label_ok:
                label_correct += 1

        expected_set = set(expected_sections)
        used_set = set(used_sections)
        hit_any = bool(expected_set & used_set) if expected_set else False
        hit_all = expected_set.issubset(used_set) if expected_set else False

        if expected_set:
            expected_total += 1
            if hit_any:
                expected_hit_any += 1
            if hit_all:
                expected_hit_all += 1

        eligible = bool(expected_set) and bool(gt_label)
        if eligible:
            contract_total += 1
            if label_ok and hit_all:
                contract_pass += 1
            else:
                failures.append(
                    {
                        "item_id": res.get("id"),
                        "question": res.get("question"),
                        "ground_truth_label": gt_label,
                        "pred_label": pred_label,
                        "expected_sections": expected_sections,
                        "used_sections": used_sections,
                        "label_ok": label_ok,
                        "expected_hit_all": hit_all,
                        "expected_hit_any": hit_any,
                    }
                )

    grounded_rate = expected_hit_any / expected_total if expected_total else 0.0
    expected_hit_rate = expected_hit_all / expected_total if expected_total else 0.0

    report: dict[str, object] = {
        "eval_json": str(eval_json),
        "summary": {
            "items": len(results),
            "label_total": label_total,
            "label_accuracy": (label_correct / label_total if label_total else 0.0),
            "expected_total": expected_total,
            "grounded_rate": grounded_rate,
            "expected_section_hit_rate": expected_hit_rate,
            "contract_total": contract_total,
            "contract_pass_rate": (
                contract_pass / contract_total if contract_total else 0.0
            ),
            "min_grounded_rate": min_grounded_rate,
            "min_expected_hit_rate": min_expected_hit_rate,
        },
        "failures": failures,
    }
    thresholds_ok = (
        grounded_rate >= min_grounded_rate
        and expected_hit_rate >= min_expected_hit_rate
    )
    report["thresholds_ok"] = thresholds_ok
    return report
