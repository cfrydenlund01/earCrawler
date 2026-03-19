from __future__ import annotations

"""Metadata normalization, tokenization, and ranking helpers for retrieval."""

import re
from collections import Counter
from math import log
from typing import Mapping

from earCrawler.rag.retriever_citation_policy import canonical_section_id

SCORE_TIE_EPSILON = 1e-6
HYBRID_RRF_K = 60
HYBRID_MIN_CANDIDATES = 20
HYBRID_CANDIDATE_MULTIPLIER = 4
BM25_K1 = 1.5
BM25_B = 0.75
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*(?:\([A-Za-z0-9]+\))*")


def metadata_row_order(row: Mapping[str, object], fallback_order: int) -> int:
    raw = row.get("row_id")
    try:
        return int(raw) if raw is not None else fallback_order
    except Exception:
        return fallback_order


def metadata_tie_break_key(
    row: Mapping[str, object], fallback_order: int
) -> tuple[str, str, int]:
    section_id = canonical_section_id(row) or ""
    chunk_or_doc_id = str(row.get("chunk_id") or row.get("doc_id") or row.get("id") or "")
    return (section_id, chunk_or_doc_id, metadata_row_order(row, fallback_order))


def score_bucket(score: object) -> int:
    try:
        return int(round(float(score) / SCORE_TIE_EPSILON))
    except Exception:
        return 0


def document_text_for_embedding(row: Mapping[str, object]) -> str:
    for key in ("text", "body", "content", "paragraph", "summary", "snippet", "title"):
        value = row.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def document_text_for_bm25(row: Mapping[str, object]) -> str:
    parts: list[str] = []
    for key in ("section_id", "doc_id", "title", "text", "body", "content", "paragraph", "summary", "snippet"):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def normalize_bm25_token(raw: str) -> str:
    token = str(raw or "").strip().lower()
    if not token:
        return ""
    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("es") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("s") and len(token) > 3:
        token = token[:-1]
    return token


def tokenize_for_bm25(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(str(text or "")):
        token = normalize_bm25_token(raw)
        if token:
            tokens.append(token)
    return tokens


def materialize_metadata_rows(metadata: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for idx, row in enumerate(metadata):
        materialized = dict(row)
        materialized.setdefault("row_id", idx)
        rows.append(materialized)
    return rows


def public_result_doc(row: Mapping[str, object]) -> dict:
    doc = dict(row)
    doc.pop("row_id", None)
    if "section_id" not in doc and doc.get("doc_id"):
        doc["section_id"] = str(doc.get("doc_id")).split("#", 1)[0]
    return doc


def result_doc_id(row: Mapping[str, object]) -> str:
    return str(row.get("doc_id") or row.get("id") or "").strip()


def build_bm25_state(metadata: list[dict]) -> dict[str, object]:
    doc_terms: list[Counter[str]] = []
    doc_lengths: list[int] = []
    doc_freq: Counter[str] = Counter()
    for row in metadata:
        terms = Counter(tokenize_for_bm25(document_text_for_bm25(row)))
        doc_terms.append(terms)
        doc_lengths.append(int(sum(terms.values())))
        doc_freq.update(terms.keys())

    doc_count = max(1, len(metadata))
    avg_doc_length = sum(doc_lengths) / doc_count if doc_lengths else 0.0
    idf = {
        term: float(log(1.0 + ((doc_count - freq + 0.5) / (freq + 0.5))))
        for term, freq in doc_freq.items()
    }
    return {
        "doc_terms": doc_terms,
        "doc_lengths": doc_lengths,
        "avg_doc_length": avg_doc_length,
        "idf": idf,
    }


def rank_bm25(
    prompt: str,
    metadata: list[dict],
    *,
    state: dict[str, object],
    k: int,
) -> list[dict]:
    query_terms = Counter(tokenize_for_bm25(prompt))
    if not query_terms:
        return []

    doc_terms = state.get("doc_terms") or []
    doc_lengths = state.get("doc_lengths") or []
    avg_doc_length = float(state.get("avg_doc_length") or 0.0)
    idf_map = state.get("idf") or {}
    denom_floor = avg_doc_length if avg_doc_length > 0 else 1.0

    ranked: list[tuple[int, float, tuple[str, str, int]]] = []
    for idx, terms in enumerate(doc_terms):
        if not isinstance(terms, Counter):
            continue
        doc_length = int(doc_lengths[idx]) if idx < len(doc_lengths) else 0
        norm = 1.0 - BM25_B + (BM25_B * (doc_length / denom_floor))
        score = 0.0
        for term, _qtf in query_terms.items():
            tf = int(terms.get(term, 0))
            if tf <= 0:
                continue
            idf = float(idf_map.get(term) or 0.0)
            if idf <= 0.0:
                continue
            score += idf * ((tf * (BM25_K1 + 1.0)) / (tf + (BM25_K1 * norm)))
        if score <= 0.0:
            continue
        ranked.append((idx, float(score), metadata_tie_break_key(metadata[idx], idx)))

    ranked.sort(key=lambda item: (-item[1], item[2]))

    results: list[dict] = []
    for idx, score, _tie_key in ranked[: max(1, int(k))]:
        doc = public_result_doc(metadata[idx])
        doc["score"] = float(score)
        doc["bm25_score"] = float(score)
        results.append(doc)
    return results


def hybrid_candidate_count(*, k: int, total_docs: int) -> int:
    requested = max(1, int(k))
    if total_docs <= 0:
        return requested
    return min(
        total_docs,
        max(HYBRID_MIN_CANDIDATES, requested * HYBRID_CANDIDATE_MULTIPLIER),
    )


def fuse_rankings(
    *,
    metadata: list[dict],
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int,
    rrf_k: int = HYBRID_RRF_K,
) -> list[dict]:
    metadata_lookup = {
        result_doc_id(row): (row, idx)
        for idx, row in enumerate(metadata)
        if result_doc_id(row)
    }
    source_docs: dict[str, dict] = {}
    for row in list(dense_results) + list(bm25_results):
        doc_id = result_doc_id(row)
        if doc_id and doc_id not in source_docs:
            source_docs[doc_id] = dict(row)

    fused_scores: dict[str, float] = {}
    details: dict[str, dict[str, float | int | str]] = {}
    for signal_name, ranking in (("dense", dense_results), ("bm25", bm25_results)):
        for rank, row in enumerate(ranking, start=1):
            doc_id = result_doc_id(row)
            if not doc_id:
                continue
            fused_scores[doc_id] = fused_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))
            info = details.setdefault(doc_id, {"retrieval_mode": "hybrid"})
            info[f"{signal_name}_rank"] = rank
            try:
                info[f"{signal_name}_score"] = float(row.get("score") or 0.0)
            except Exception:
                pass

    ranked_doc_ids = list(fused_scores.keys())
    ranked_doc_ids.sort(
        key=lambda doc_id: (
            -fused_scores.get(doc_id, 0.0),
            metadata_tie_break_key(*metadata_lookup[doc_id])
            if doc_id in metadata_lookup
            else (doc_id, "", 0),
        )
    )

    fused: list[dict] = []
    for doc_id in ranked_doc_ids[: max(1, int(k))]:
        if doc_id in metadata_lookup:
            base_doc = public_result_doc(metadata_lookup[doc_id][0])
        else:
            base_doc = dict(source_docs.get(doc_id) or {})
        base_doc["score"] = float(fused_scores[doc_id])
        base_doc["fusion_score"] = float(fused_scores[doc_id])
        for key, value in details.get(doc_id, {}).items():
            base_doc[key] = value
        fused.append(base_doc)
    return fused


__all__ = [
    "HYBRID_RRF_K",
    "build_bm25_state",
    "document_text_for_bm25",
    "document_text_for_embedding",
    "fuse_rankings",
    "hybrid_candidate_count",
    "materialize_metadata_rows",
    "metadata_tie_break_key",
    "public_result_doc",
    "rank_bm25",
    "result_doc_id",
    "score_bucket",
    "tokenize_for_bm25",
]
