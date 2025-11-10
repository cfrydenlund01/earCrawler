from __future__ import annotations

import math
import time

from fastapi import APIRouter, Depends, Request

from ..fuseki import FusekiGateway
from ..schemas import (
    CacheState,
    LineageEdge,
    ProblemDetails,
    RagAnswer,
    RagLineageReference,
    RagQueryRequest,
    RagResponse,
    RagSource,
)
from ..rag_support import RagQueryCache, RetrieverProtocol
from .dependencies import get_gateway, get_rag_cache, get_retriever, rate_limit

router = APIRouter(prefix="/v1", tags=["rag"])


@router.post("/rag/query", response_model=RagResponse, responses={429: {"model": ProblemDetails}})
async def rag_query(
    payload: RagQueryRequest,
    request: Request,
    gateway: FusekiGateway = Depends(get_gateway),
    retriever: RetrieverProtocol = Depends(get_retriever),
    cache: RagQueryCache = Depends(get_rag_cache),
    _: None = Depends(rate_limit("rag")),
) -> RagResponse:
    start = time.perf_counter()
    cache_key = payload.cache_key()
    cached = cache.get(cache_key)
    cache_hit = cached is not None
    documents = cached if cache_hit else retriever.query(payload.query, k=payload.top_k)
    if not cache_hit:
        expires_at = cache.put(cache_key, documents)
    else:
        expires_at = cache.expires_at(cache_key)

    results = []
    for doc in documents:
        result = await _build_answer(doc, gateway, payload.include_lineage)
        results.append(result)

    trace_id = getattr(request.state, "trace_id", "")
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    cache_state = CacheState(hit=cache_hit, expires_at=expires_at)
    return RagResponse(
        trace_id=trace_id,
        latency_ms=latency_ms,
        query=payload.query,
        cache=cache_state,
        results=results,
    )


async def _build_answer(doc: dict, gateway: FusekiGateway, include_lineage: bool) -> RagAnswer:
    content = str(
        doc.get("text")
        or doc.get("content")
        or doc.get("paragraph")
        or doc.get("body")
        or doc.get("snippet")
        or ""
    ).strip()
    score = _coerce_score(doc.get("score"))
    source = RagSource(
        id=_maybe_str(doc.get("id") or doc.get("entity_id") or doc.get("section")),
        url=_maybe_str(doc.get("source_url") or doc.get("url")),
        label=_maybe_str(doc.get("title") or doc.get("label")),
        section=_maybe_str(doc.get("section")),
        provider=_maybe_str(doc.get("provider")),
    )
    lineage: RagLineageReference | None = None
    if include_lineage:
        lineage_id = source.id or _maybe_str(doc.get("lineage_id"))
        if lineage_id:
            edges = await _lineage_edges(gateway, lineage_id)
            if edges:
                lineage = RagLineageReference(entity_id=lineage_id, edges=edges)
    return RagAnswer(content=content, score=score, source=source, lineage=lineage)


async def _lineage_edges(gateway: FusekiGateway, entity_id: str) -> list[LineageEdge]:
    rows = await gateway.select("lineage_by_id", {"id": entity_id})
    edges: list[LineageEdge] = []
    for row in rows:
        source = _maybe_str(row.get("source")) or entity_id
        target = _maybe_str(row.get("target"))
        relation = _maybe_str(row.get("relation"))
        timestamp = row.get("timestamp")
        if isinstance(timestamp, dict) and "value" in timestamp:
            timestamp = timestamp["value"]
        if not (target and relation):
            continue
        edges.append(LineageEdge(source=source, relation=relation, target=target, timestamp=_maybe_str(timestamp)))
    return edges


def _maybe_str(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _coerce_score(value: object) -> float:
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        try:
            num = float(value)
        except ValueError:
            num = 0.0
    else:
        num = 0.0
    if math.isnan(num) or math.isinf(num):
        num = 0.0
    if num > 1.0:
        num = min(1.0, num / 100.0 if num > 10 else num)
    if num < 0:
        num = 0.0
    return round(num, 4)


__all__ = ["router"]
