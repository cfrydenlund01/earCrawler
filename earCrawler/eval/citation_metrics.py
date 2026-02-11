from __future__ import annotations

"""Citation precision/recall helpers for eval harnesses.

This module stays deterministic and offline. It canonicalizes EAR section ids
the same way the RAG pipeline does and returns lightweight dataclasses that can
be embedded directly in eval artifacts without breaking existing schemas.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from earCrawler.rag.pipeline import _normalize_section_id


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted({v for v in values if v})


@dataclass
class CitationScore:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    predicted: list[str]
    ground_truth: list[str]
    errors: list[dict]


def _compute_precision(tp: int, fp: int, *, gt_count: int) -> float:
    if tp + fp == 0:
        # No predictions: perfect precision only if there was nothing to cite.
        return 1.0 if gt_count == 0 else 0.0
    return tp / (tp + fp)


def _compute_recall(tp: int, fn: int, *, gt_count: int) -> float:
    if gt_count == 0:
        return 1.0
    if tp + fn == 0:
        return 0.0
    return tp / (tp + fn)


def extract_ground_truth_sections(
    item: Mapping[str, object], dataset_refs: Mapping[str, object] | None = None
) -> set[str]:
    """Collect canonical section ids that represent ground-truth citations.

    Precedence (stop when a non-empty set is found):
    1) evidence.doc_spans span_id values
    2) item.expected_sections or ear_sections (if present)
    3) manifest references.sections (fallback when evidence is missing)
    """

    sections: set[str] = set()

    evidence = item.get("evidence") or {}
    doc_ids: set[str] = set()
    for span in evidence.get("doc_spans") or []:
        if span.get("doc_id"):
            doc_ids.add(str(span.get("doc_id")))
        norm = _normalize_section_id(span.get("span_id"))
        if norm:
            sections.add(norm)
    if sections:
        return sections

    for key in ("expected_sections", "ear_sections"):
        for sec in item.get(key) or []:
            norm = _normalize_section_id(sec)
            if norm:
                sections.add(norm)
    if sections:
        return sections

    refs = dataset_refs.get("sections") if isinstance(dataset_refs, Mapping) else None
    if doc_ids and isinstance(refs, Mapping):
        for doc_id, span_list in refs.items():
            if str(doc_id) not in doc_ids:
                continue
            for span in span_list or []:
                raw = span
                if isinstance(span, Mapping):
                    raw = (
                        span.get("id")
                        or span.get("section_id")
                        or span.get("span_id")
                        or span.get("value")
                    )
                norm = _normalize_section_id(raw)
                if norm:
                    sections.add(norm)
    return sections


def extract_predicted_sections(result_item: Mapping[str, object]) -> set[str]:
    """Canonicalize predicted citation ids.

    Use explicit citations[] only. Missing citations must remain missing so
    eval outputs do not silently convert retrieval hits into citation passes.
    """

    sections: set[str] = set()
    for cit in result_item.get("citations") or []:
        norm = _normalize_section_id(cit.get("section_id"))
        if norm:
            sections.add(norm)
    return sections


def score_citations(
    pred: set[str], gt: set[str], *, errors: Sequence[Mapping[str, object]] | None = None
) -> CitationScore:
    tp = len(pred & gt)
    fp = len(pred - gt)
    fn = len(gt - pred)

    precision = _compute_precision(tp, fp, gt_count=len(gt))
    recall = _compute_recall(tp, fn, gt_count=len(gt))
    denom = precision + recall
    f1 = (2 * precision * recall / denom) if denom else (1.0 if not (pred or gt) else 0.0)

    return CitationScore(
        precision=precision,
        recall=recall,
        f1=f1,
        tp=tp,
        fp=fp,
        fn=fn,
        predicted=_sorted_unique(pred),
        ground_truth=_sorted_unique(gt),
        errors=list(errors or []),
    )


__all__ = [
    "CitationScore",
    "extract_ground_truth_sections",
    "extract_predicted_sections",
    "score_citations",
]
