from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import median
from typing import Callable, Iterable, Mapping, Sequence

from earCrawler.eval.evidence_resolver import load_corpus_index
from earCrawler.rag.pipeline import _normalize_section_id


def _base_section_id(value: str) -> str:
    """Return the base section id without subsection suffixes.

    Example:
    - EAR-740.9(a)(2) -> EAR-740.9
    - EAR-736.2#p0001 -> EAR-736.2  (caller should normalize '#' first)
    """

    return str(value).split("(", 1)[0].strip()


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)


def _resolve_dataset_path(manifest_path: Path, dataset_entry: Mapping[str, object]) -> Path:
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


def _dataset_is_v2(entry: Mapping[str, object]) -> bool:
    ds_id = str(entry.get("id") or "")
    if ds_id.endswith(".v2"):
        return True
    try:
        return int(entry.get("version") or 0) >= 2
    except Exception:
        return False


def _read_index_meta(index_path: str | None) -> dict[str, object] | None:
    if not index_path:
        return None
    path = Path(index_path)
    meta_path = path.with_suffix(".meta.json")
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    snapshot = payload.get("snapshot")
    if snapshot is not None and not isinstance(snapshot, dict):
        snapshot = None
    return {
        "meta_path": str(meta_path),
        "schema_version": payload.get("schema_version"),
        "corpus_schema_version": payload.get("corpus_schema_version"),
        "corpus_digest": payload.get("corpus_digest"),
        "snapshot": snapshot,
    }


def build_fr_coverage_summary(
    report: Mapping[str, object], *, top_missing_sections: int = 10
) -> dict[str, object]:
    """Extract a compact, machine-readable summary suitable for CI/artifacts."""

    datasets: Sequence[Mapping[str, object]] = report.get("datasets") or []
    retriever: Mapping[str, object] = report.get("retriever") or {}
    summary_obj: Mapping[str, object] = report.get("summary") or {}

    ds_summaries: list[dict[str, object]] = []
    for ds in datasets:
        ds_sum: Mapping[str, object] = ds.get("summary") or {}
        ds_summaries.append(
            {
                "dataset_id": ds.get("dataset_id"),
                "num_items": ds_sum.get("num_items"),
                "expected_sections": ds_sum.get("expected_sections"),
                "num_missing_in_corpus": ds_sum.get("missing_in_corpus"),
                "num_missing_in_retrieval": ds_sum.get("missing_in_retrieval"),
                "missing_in_retrieval_rate": ds_sum.get("missing_in_retrieval_rate"),
                "top_missing_sections": ds.get("top_missing_sections") or [],
            }
        )

    def _rate(row: Mapping[str, object]) -> float:
        try:
            return float(row.get("missing_in_retrieval_rate") or 0.0)
        except Exception:
            return 0.0

    ds_summaries.sort(key=_rate, reverse=True)

    return {
        "manifest_path": report.get("manifest_path"),
        "corpus_path": report.get("corpus_path"),
        "retrieval_k": report.get("retrieval_k"),
        "dataset_selector": report.get("dataset_selector") or {},
        "retriever": {
            "index_path": retriever.get("index_path"),
            "model_name": retriever.get("model_name"),
            "index_meta": retriever.get("index_meta"),
        },
        "summary": {
            "num_datasets": summary_obj.get("num_datasets"),
            "num_items": summary_obj.get("num_items"),
            "expected_sections": summary_obj.get("expected_sections"),
            "num_missing_in_corpus": summary_obj.get("missing_in_corpus"),
            "num_missing_in_retrieval": summary_obj.get("missing_in_retrieval"),
            "missing_in_retrieval_rate": summary_obj.get("missing_in_retrieval_rate"),
            "worst_dataset_id": summary_obj.get("worst_dataset_id"),
            "worst_missing_in_retrieval_rate": summary_obj.get(
                "worst_missing_in_retrieval_rate"
            ),
            "top_missing_sections": summary_obj.get("top_missing_sections") or [],
        },
        "datasets": ds_summaries,
    }


def render_fr_coverage_blocker_note(
    report: Mapping[str, object],
    *,
    max_missing_rate: float | None = None,
    top_missing_sections: int = 10,
) -> str:
    """Generate a deterministic Markdown note explaining Phase 1 blockers."""

    summary = report.get("summary") or {}
    selector = report.get("dataset_selector") or {}
    retriever = report.get("retriever") or {}

    def _fmt_rate(val: object) -> str:
        try:
            return f"{float(val):.4f}"
        except Exception:
            return "0.0000"

    threshold_line = (
        f"{max_missing_rate:.2%}" if isinstance(max_missing_rate, float) else "n/a"
    )
    overall_rate = _fmt_rate(summary.get("missing_in_retrieval_rate"))
    worst_rate = _fmt_rate(summary.get("worst_missing_in_retrieval_rate"))
    worst_ds = summary.get("worst_dataset_id") or "n/a"

    top_missing = summary.get("top_missing_sections") or []
    top_missing = list(top_missing)[:top_missing_sections]

    missing_in_corpus = int(summary.get("missing_in_corpus") or 0)
    missing_in_retrieval = int(summary.get("missing_in_retrieval") or 0)

    hypothesis: list[str] = []
    if missing_in_corpus:
        hypothesis.append(
            "Some expected section ids are not present in the FR corpus JSONL (corpus/content gap)."
        )
    if missing_in_retrieval:
        hypothesis.append(
            "Expected section ids exist but are not returned in top-K (index coverage, chunking, or id normalization mismatch)."
        )
    if not hypothesis:
        hypothesis.append("No blocker detected from this report.")

    next_actions: list[str] = [
        "Rebuild retrieval corpus from an authoritative offline snapshot and rebuild the FAISS index.",
        "Verify section-id normalization: dataset `ear_sections` / `evidence.doc_spans.span_id` should match retriever `section_id` after normalization.",
        "Inspect top missing section ids below; confirm they exist in the corpus and are chunked/indexed with the same canonical ids.",
    ]

    index_path = retriever.get("index_path") or "data/faiss/index.faiss"
    model_name = retriever.get("model_name") or "all-MiniLM-L12-v2"

    lines: list[str] = []
    lines.append("# Phase 1 retrieval-coverage blocker note")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- dataset_selector: `{json.dumps(selector, sort_keys=True)}`")
    lines.append(f"- retrieval_k: `{report.get('retrieval_k')}`")
    lines.append(f"- corpus_path: `{report.get('corpus_path')}`")
    lines.append(f"- retriever.index_path: `{index_path}`")
    lines.append(f"- retriever.model_name: `{model_name}`")
    lines.append("")
    lines.append("## Results")
    lines.append(f"- max_missing_rate threshold: `{threshold_line}`")
    lines.append(f"- overall missing_in_retrieval_rate: `{overall_rate}`")
    lines.append(f"- worst dataset: `{worst_ds}` (missing_in_retrieval_rate `{worst_rate}`)")
    lines.append(
        f"- counts: missing_in_corpus `{missing_in_corpus}`, missing_in_retrieval `{missing_in_retrieval}`"
    )
    lines.append("")
    lines.append("## Top missing section ids")
    if top_missing:
        for row in top_missing:
            if isinstance(row, Mapping):
                sec = row.get("section_id")
                cnt = row.get("count")
                lines.append(f"- `{sec}`: `{cnt}`")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Root cause hypothesis (data-driven)")
    for h in hypothesis:
        lines.append(f"- {h}")
    lines.append("")
    lines.append("## Next actions")
    for a in next_actions:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("## Rebuild commands (offline)")
    lines.append(
        "- Build retrieval corpus: `python -m earCrawler.cli rag_index build-corpus --snapshot <ecfr_snapshot.jsonl> --out data/faiss/retrieval_corpus.jsonl`"
    )
    lines.append(
        f"- Build FAISS index: `python -m earCrawler.cli rag_index build --input data/faiss/retrieval_corpus.jsonl --index-path \"{index_path}\" --model-name \"{model_name}\"`"
    )
    lines.append("")
    return "\n".join(lines)


def build_fr_coverage_report(
    *,
    manifest: Path,
    corpus: Path,
    dataset_id: str = "all",
    only_v2: bool = False,
    dataset_id_pattern: str | None = None,
    retrieval_k: int = 10,
    max_items: int | None = None,
    retrieve_context: Callable[[str, int], Sequence[Mapping[str, object]]] | None = None,
    top_missing_sections: int = 10,
) -> dict[str, object]:
    """Build a report that checks FR section coverage + FAISS retrievability.

    Intended behavior
    - Enumerate expected EAR sections from each dataset item (ear_sections + evidence.doc_spans).
    - Verify each expected section exists in the FR corpus (data/fr_sections.jsonl).
    - Query the FAISS retriever with the question and record the rank (1-based) of each expected section.
    """

    manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    dataset_entries = manifest_obj.get("datasets", []) or []
    if dataset_id != "all":
        dataset_entries = [entry for entry in dataset_entries if entry.get("id") == dataset_id]
    if only_v2:
        dataset_entries = [entry for entry in dataset_entries if _dataset_is_v2(entry)]
    if dataset_id_pattern:
        try:
            pattern = re.compile(dataset_id_pattern)
        except re.error as exc:
            raise ValueError(f"Invalid dataset id pattern: {exc}") from exc
        dataset_entries = [
            entry for entry in dataset_entries if pattern.search(str(entry.get("id") or ""))
        ]
    if not dataset_entries:
        raise ValueError("No datasets matched selection (dataset_id/only_v2/pattern).")

    corpus_index = load_corpus_index(corpus)

    retriever_details: dict[str, object] | None = None
    if retrieve_context is None:
        from earCrawler.rag.pipeline import _ensure_retriever, retrieve_regulation_context
        from earCrawler.rag.retriever import describe_retriever_config

        try:
            retriever_obj = _ensure_retriever()
        except Exception as exc:
            raise RuntimeError(
                "FAISS retriever unavailable (failed to initialize). Fix by building an offline index and/or "
                "setting env vars:\n"
                "- Build corpus: `python -m earCrawler.cli rag_index build-corpus --snapshot <ecfr_snapshot.jsonl> --out data/faiss/retrieval_corpus.jsonl`\n"
                "- Build index: `python -m earCrawler.cli rag_index build --input data/faiss/retrieval_corpus.jsonl --index-path data/faiss/index.faiss`\n"
                "- Optional overrides: EARCRAWLER_FAISS_INDEX, EARCRAWLER_FAISS_MODEL\n"
                "- If you see a Windows torch/shm.dll loader error, repair/reinstall PyTorch in the active environment.\n"
                f"Underlying error: {exc}"
            ) from exc
        if retriever_obj is None:
            raise RuntimeError(
                "FAISS retriever unavailable. Fix by building an offline index and/or setting env vars:\n"
                "- Build corpus: `python -m earCrawler.cli rag_index build-corpus --snapshot <ecfr_snapshot.jsonl> --out data/faiss/retrieval_corpus.jsonl`\n"
                "- Build index: `python -m earCrawler.cli rag_index build --input data/faiss/retrieval_corpus.jsonl --index-path data/faiss/index.faiss`\n"
                "- Optional overrides: EARCRAWLER_FAISS_INDEX, EARCRAWLER_FAISS_MODEL"
            )
        retriever_details = describe_retriever_config(retriever_obj)
        index_path = retriever_details.get("index_path")
        if isinstance(index_path, str):
            retriever_details["index_meta"] = _read_index_meta(index_path)

        def retrieve_context(question: str, k: int) -> Sequence[Mapping[str, object]]:
            return retrieve_regulation_context(question, top_k=k, retriever=retriever_obj)

    report: dict[str, object] = {
        "manifest_path": str(manifest),
        "corpus_path": str(corpus),
        "dataset_selector": {
            "dataset_id": dataset_id,
            "only_v2": bool(only_v2),
            "dataset_id_pattern": dataset_id_pattern,
        },
        "retrieval_k": retrieval_k,
        "retriever": retriever_details or {},
        "datasets": [],
    }

    total_expected = 0
    total_missing_in_corpus = 0
    total_missing_in_retrieval = 0
    hit_ranks: list[int] = []
    total_items = 0
    global_missing_counts: dict[str, int] = {}

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
        ds_items = 0
        ds_missing_counts: dict[str, int] = {}

        for idx, item in enumerate(_iter_jsonl(data_file)):
            if max_items is not None and idx >= max_items:
                break
            ds_items += 1
            question = str(item.get("question") or "")
            expected_sections = _expected_sections_for_item(item)
            missing_in_corpus = [sec for sec in expected_sections if sec not in corpus_index]

            retrieved = list(retrieve_context(question, retrieval_k))
            retrieved_sections: list[str] = []
            for rec in retrieved:
                sec = rec.get("section_id") if isinstance(rec, Mapping) else None
                norm = _normalize_section_id(sec)
                if norm:
                    retrieved_sections.append(norm)

            ranks: dict[str, int | None] = {sec: None for sec in expected_sections}
            base_ranks: dict[str, int] = {}
            for rank, sec in enumerate(retrieved_sections, start=1):
                base_ranks.setdefault(_base_section_id(sec), rank)
                if sec in ranks and ranks[sec] is None:
                    ranks[sec] = rank

            # When the expected universe is section-level (EAR-740.9), count hits on any
            # subsection (EAR-740.9(a), EAR-740.9(a)(2), ...) as coverage.
            for expected in expected_sections:
                if ranks[expected] is not None:
                    continue
                if "(" in expected:
                    continue
                ranks[expected] = base_ranks.get(expected)

            missing_in_retrieval = [sec for sec, rank in ranks.items() if rank is None]
            rank_values = [rank for rank in ranks.values() if isinstance(rank, int)]

            ds_expected += len(expected_sections)
            ds_missing_in_corpus += len(missing_in_corpus)
            ds_missing_in_retrieval += len(missing_in_retrieval)
            ds_rank_hits.extend(rank_values)

            for sec in missing_in_retrieval:
                ds_missing_counts[sec] = ds_missing_counts.get(sec, 0) + 1
                global_missing_counts[sec] = global_missing_counts.get(sec, 0) + 1

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

        missing_rate = (ds_missing_in_retrieval / ds_expected) if ds_expected else 0.0
        top_missing = sorted(
            (
                {"section_id": sec, "count": cnt}
                for sec, cnt in ds_missing_counts.items()
            ),
            key=lambda row: (-int(row["count"]), str(row["section_id"])),
        )[: max(0, int(top_missing_sections))]

        dataset_report = {
            "dataset_id": ds_id,
            "file": str(data_file),
            "items": item_reports,
            "summary": {
                "num_items": ds_items,
                "expected_sections": ds_expected,
                "missing_in_corpus": ds_missing_in_corpus,
                "missing_in_retrieval": ds_missing_in_retrieval,
                "missing_in_retrieval_rate": missing_rate,
                "median_retrieval_rank": (median(ds_rank_hits) if ds_rank_hits else None),
            },
            "top_missing_sections": top_missing,
        }
        report["datasets"].append(dataset_report)

        total_items += ds_items
        total_expected += ds_expected
        total_missing_in_corpus += ds_missing_in_corpus
        total_missing_in_retrieval += ds_missing_in_retrieval
        hit_ranks.extend(ds_rank_hits)

    overall_missing_rate = (
        (total_missing_in_retrieval / total_expected) if total_expected else 0.0
    )
    worst_ds_id: str | None = None
    worst_rate = 0.0
    for ds in report["datasets"]:
        ds_sum = ds.get("summary") or {}
        try:
            ds_rate = float(ds_sum.get("missing_in_retrieval_rate") or 0.0)
        except Exception:
            ds_rate = 0.0
        if worst_ds_id is None or ds_rate > worst_rate:
            worst_rate = ds_rate
            worst_ds_id = str(ds.get("dataset_id") or "")

    top_missing_all = sorted(
        ({"section_id": sec, "count": cnt} for sec, cnt in global_missing_counts.items()),
        key=lambda row: (-int(row["count"]), str(row["section_id"])),
    )[: max(0, int(top_missing_sections))]

    report["summary"] = {
        "num_datasets": len(report["datasets"]),
        "num_items": total_items,
        "expected_sections": total_expected,
        "missing_in_corpus": total_missing_in_corpus,
        "missing_in_retrieval": total_missing_in_retrieval,
        "missing_in_retrieval_rate": overall_missing_rate,
        "median_retrieval_rank": (median(hit_ranks) if hit_ranks else None),
        "worst_dataset_id": worst_ds_id,
        "worst_missing_in_retrieval_rate": worst_rate,
        "top_missing_sections": top_missing_all,
    }
    return report


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
            "contract_pass_rate": (contract_pass / contract_total if contract_total else 0.0),
            "min_grounded_rate": min_grounded_rate,
            "min_expected_hit_rate": min_expected_hit_rate,
        },
        "failures": failures,
    }
    thresholds_ok = grounded_rate >= min_grounded_rate and expected_hit_rate >= min_expected_hit_rate
    report["thresholds_ok"] = thresholds_ok
    return report
