from __future__ import annotations

import math
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..fuseki import FusekiGateway
from api_clients.llm_client import LLMProviderError, generate_chat
from earCrawler.config.llm_secrets import get_llm_config
from ..schemas import (
    CacheState,
    LineageEdge,
    ProblemDetails,
    RagAnswer,
    RagGeneratedResponse,
    RagLineageReference,
    RagQueryRequest,
    RagResponse,
    RetrievedDocument,
    RagSource,
)
from ..rag_support import RagQueryCache, RetrieverProtocol, NullRetriever
from .dependencies import (
    get_gateway,
    get_rag_cache,
    get_retriever,
    rate_limit,
)

router = APIRouter(prefix="/v1", tags=["rag"])


@router.post(
    "/rag/query", response_model=RagResponse, responses={429: {"model": ProblemDetails}}
)
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


async def _build_answer(
    doc: dict, gateway: FusekiGateway, include_lineage: bool
) -> RagAnswer:
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
        edges.append(
            LineageEdge(
                source=source,
                relation=relation,
                target=target,
                timestamp=_maybe_str(timestamp),
            )
        )
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


def _to_retrieved_document(doc: dict) -> RetrievedDocument:
    return RetrievedDocument(
        id=_maybe_str(doc.get("id") or doc.get("entity_id") or doc.get("section")),
        score=_coerce_score(doc.get("score")),
        title=_maybe_str(doc.get("title") or doc.get("label")),
        url=_maybe_str(doc.get("source_url") or doc.get("url")),
        section=_maybe_str(doc.get("section")),
        provider=_maybe_str(doc.get("provider")),
    )


@router.post(
    "/rag/answer",
    response_model=RagGeneratedResponse,
    responses={
        429: {"model": ProblemDetails},
        503: {"model": RagGeneratedResponse},
    },
)
async def rag_answer(
    payload: RagQueryRequest,
    request: Request,
    retriever: RetrieverProtocol = Depends(get_retriever),
    cache: RagQueryCache = Depends(get_rag_cache),
    _: None = Depends(rate_limit("rag")),
) -> JSONResponse:
    start = time.perf_counter()
    cache_key = payload.cache_key()
    rag_enabled = not isinstance(retriever, NullRetriever)

    documents: list[dict] = []
    cache_hit = False
    expires_at = None
    if rag_enabled:
        cached = cache.get(cache_key)
        cache_hit = cached is not None
        documents = cached if cache_hit else retriever.query(
            payload.query, k=payload.top_k
        )
        expires_at = cache.expires_at(cache_key) if cache_hit else cache.put(
            cache_key, documents
        )

    disabled_reason = None
    contexts: list[str] = []
    answer: str | None = None
    status_code = 200
    model_label = None
    provider_label = None
    llm_enabled = False

    if not rag_enabled:
        disabled_reason = "RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1"
        status_code = 503
    else:
        try:
            cfg = get_llm_config()
            provider_label = cfg.provider.provider
            model_label = cfg.provider.model
            prompt_contexts: list[str] = []
            for doc in documents:
                text = str(
                    doc.get("text")
                    or doc.get("content")
                    or doc.get("paragraph")
                    or doc.get("body")
                    or doc.get("snippet")
                    or ""
                ).strip()
                if not text:
                    continue
                section = str(
                    doc.get("section")
                    or doc.get("span_id")
                    or doc.get("id")
                    or doc.get("entity_id")
                    or ""
                ).strip()
                prefix = f"[{section}] " if section else ""
                prompt_contexts.append(prefix + text)
            contexts = prompt_contexts
            system = (
                "You are an expert export compliance assistant focused on the Export Administration Regulations (EAR). "
                "Answer using ONLY the provided context excerpts. "
                "When you make a claim, cite the relevant excerpt by referencing its bracketed section id if present."
            )
            context_block = "\n\n".join(prompt_contexts) if prompt_contexts else "No supporting context provided."
            user = f"Context:\n{context_block}\n\nQuestion: {payload.query}\nAnswer:"
            answer = generate_chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}]
            ).strip()
            llm_enabled = True
            if not answer:
                disabled_reason = "LLM did not return an answer"
                llm_enabled = False
                status_code = 503
        except LLMProviderError as exc:
            disabled_reason = str(exc)
            llm_enabled = False
            status_code = 503
        except Exception as exc:  # pragma: no cover - defensive
            disabled_reason = str(exc)
            llm_enabled = False
            status_code = 503

    trace_id = getattr(request.state, "trace_id", "")
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    cache_state = CacheState(
        hit=cache_hit if rag_enabled else False, expires_at=expires_at
    )
    retrieved = [_to_retrieved_document(doc) for doc in documents]
    response = RagGeneratedResponse(
        trace_id=trace_id,
        latency_ms=latency_ms,
        question=payload.query,
        answer=answer,
        contexts=contexts,
        retrieved=retrieved,
        model=model_label,
        provider=provider_label,
        rag_enabled=rag_enabled,
        llm_enabled=llm_enabled,
        disabled_reason=disabled_reason,
        cache=cache_state,
    )
    return JSONResponse(
        status_code=status_code, content=response.model_dump(mode="json")
    )


__all__ = ["router"]
