from __future__ import annotations

import asyncio
import logging
import time

from api_clients.llm_client import generate_chat
from earCrawler.rag import llm_runtime
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from ..fuseki import FusekiGateway
from ..rag_service import (
    build_query_answers,
    execute_answer_generation,
    retrieve_documents,
    to_retrieved_document,
)
from ..rag_support import RagQueryCache, RetrieverProtocol
from ..schemas import CacheState, ProblemDetails, RagGeneratedResponse, RagQueryRequest, RagResponse
from .dependencies import (
    get_gateway,
    get_rag_cache,
    get_retriever,
    rate_limit,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["rag"])



def _log_retrieval(request: Request, event: str, trace_id: str, **details) -> None:
    request_logger = getattr(request.app.state, "request_logger", None)
    if request_logger:
        request_logger.info(event, trace_id=trace_id, details=details)
    else:  # pragma: no cover - fallback for tests
        logger.info("%s %s", event, details)



def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


async def _run_retriever_query(
    retriever: RetrieverProtocol, query: str, top_k: int
) -> list[dict]:
    return await asyncio.to_thread(retriever.query, query, top_k)


async def _run_generate_chat(
    prompt: list[dict[str, str]] | list[dict], provider: str, model: str
) -> str:
    return await asyncio.to_thread(
        generate_chat,
        prompt,
        provider=provider,
        model=model,
    )


@router.post(
    "/rag/query",
    response_model=RagResponse,
    responses={429: {"model": ProblemDetails}, 503: {"model": ProblemDetails}},
)
async def rag_query(
    payload: RagQueryRequest,
    request: Request,
    gateway: FusekiGateway = Depends(get_gateway),
    retriever: RetrieverProtocol = Depends(get_retriever),
    cache: RagQueryCache = Depends(get_rag_cache),
    _: None = Depends(rate_limit("rag")),
) -> RagResponse:
    start_total = time.perf_counter()
    trace_id = getattr(request.state, "trace_id", "")
    retrieval = await retrieve_documents(
        query=payload.query,
        top_k=payload.top_k,
        effective_date=payload.effective_date,
        cache_key=payload.cache_key(),
        retriever=retriever,
        cache=cache,
        run_query=_run_retriever_query,
    )

    if not retrieval.rag_enabled:
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/retrieval",
            title="Retriever disabled",
            status=503,
            detail=retrieval.disabled_reason,
            instance=str(request.url),
            trace_id=trace_id,
        )
        _log_retrieval(
            request,
            "rag.query.disabled",
            trace_id,
            rag_enabled=retrieval.rag_enabled,
            retriever_ready=retrieval.retriever_ready,
            retrieval_doc_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=retrieval.retrieval_empty_reason,
            failure_type=retrieval.failure_type,
            index_path=retrieval.index_path,
            model_name=retrieval.model_name,
        )
        _log_retrieval(
            request,
            "rag.query.latency",
            trace_id,
            t_total_ms=_elapsed_ms(start_total),
            t_retrieve_ms=retrieval.t_retrieve_ms,
            t_cache_ms=retrieval.t_cache_ms,
            t_prompt_ms=0.0,
            t_llm_ms=0.0,
            t_parse_ms=0.0,
            rag_enabled=retrieval.rag_enabled,
            retriever_ready=retrieval.retriever_ready,
            retrieved_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=retrieval.retrieval_empty_reason,
        )
        return JSONResponse(status_code=503, content=problem.model_dump(exclude_none=True))

    if retrieval.retrieval_failure is not None:
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/retrieval",
            title="Retriever unavailable",
            status=503,
            detail=str(retrieval.retrieval_failure),
            instance=str(request.url),
            trace_id=trace_id,
        )
        _log_retrieval(
            request,
            "rag.query.failed",
            trace_id,
            rag_enabled=retrieval.rag_enabled,
            retriever_ready=retrieval.retriever_ready,
            retrieval_doc_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=retrieval.retrieval_empty_reason,
            failure_type=retrieval.failure_type,
            index_path=retrieval.index_path,
            model_name=retrieval.model_name,
        )
        _log_retrieval(
            request,
            "rag.query.latency",
            trace_id,
            t_total_ms=_elapsed_ms(start_total),
            t_retrieve_ms=retrieval.t_retrieve_ms,
            t_cache_ms=retrieval.t_cache_ms,
            t_prompt_ms=0.0,
            t_llm_ms=0.0,
            t_parse_ms=0.0,
            rag_enabled=retrieval.rag_enabled,
            retriever_ready=retrieval.retriever_ready,
            retrieved_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=retrieval.retrieval_empty_reason,
        )
        return JSONResponse(status_code=503, content=problem.model_dump(exclude_none=True))

    results = await build_query_answers(
        retrieval.documents,
        gateway=gateway,
        include_lineage=payload.include_lineage,
    )

    latency_ms = _elapsed_ms(start_total)
    cache_state = CacheState(hit=retrieval.cache_hit, expires_at=retrieval.expires_at)
    _log_retrieval(
        request,
        "rag.query.success",
        trace_id,
        rag_enabled=retrieval.rag_enabled,
        retriever_ready=retrieval.retriever_ready,
        retrieval_doc_count=len(retrieval.documents),
        retrieval_empty=retrieval.retrieval_empty,
        retrieval_empty_reason=retrieval.retrieval_empty_reason,
        failure_type=retrieval.failure_type,
        index_path=retrieval.index_path,
        model_name=retrieval.model_name,
    )
    _log_retrieval(
        request,
        "rag.query.latency",
        trace_id,
        t_total_ms=latency_ms,
        t_retrieve_ms=retrieval.t_retrieve_ms,
        t_cache_ms=retrieval.t_cache_ms,
        t_prompt_ms=0.0,
        t_llm_ms=0.0,
        t_parse_ms=0.0,
        rag_enabled=retrieval.rag_enabled,
        retriever_ready=retrieval.retriever_ready,
        retrieved_count=len(retrieval.documents),
        retrieval_empty=retrieval.retrieval_empty,
        retrieval_empty_reason=retrieval.retrieval_empty_reason,
    )
    return RagResponse(
        trace_id=trace_id,
        latency_ms=latency_ms,
        query=payload.query,
        cache=cache_state,
        results=results,
        retrieval_empty=retrieval.retrieval_empty,
        retrieval_empty_reason=retrieval.retrieval_empty_reason,
    )


@router.post(
    "/rag/answer",
    response_model=RagGeneratedResponse,
    responses={
        429: {"model": ProblemDetails},
        422: {"model": RagGeneratedResponse},
        503: {"model": RagGeneratedResponse},
    },
)
async def rag_answer(
    payload: RagQueryRequest,
    request: Request,
    generate: bool | None = Query(
        default=None,
        description="When false, return retrieval-only output without calling an LLM",
    ),
    retriever: RetrieverProtocol = Depends(get_retriever),
    cache: RagQueryCache = Depends(get_rag_cache),
    _: None = Depends(rate_limit("rag")),
) -> JSONResponse:
    start_total = time.perf_counter()
    trace_id = getattr(request.state, "trace_id", "")
    generate_enabled = payload.generate if generate is None else bool(generate)
    retrieval = await retrieve_documents(
        query=payload.query,
        top_k=payload.top_k,
        effective_date=payload.effective_date,
        cache_key=payload.cache_key(),
        retriever=retriever,
        cache=cache,
        run_query=_run_retriever_query,
    )

    contexts: list[str] = []
    if retrieval.retrieval_failure is not None:
        generation = llm_runtime.build_generation_disabled_result(
            question=payload.query,
            disabled_reason=str(retrieval.retrieval_failure),
            trace_id=trace_id,
        )
        generation.output_ok = False
        generation.output_error = {
            "code": retrieval.failure_type or "retriever_error",
            "message": str(retrieval.retrieval_failure),
            "details": {},
        }
        status_code = 503
    elif not retrieval.rag_enabled:
        generation = llm_runtime.build_generation_disabled_result(
            question=payload.query,
            disabled_reason=retrieval.disabled_reason or "RAG retriever disabled",
            trace_id=trace_id,
        )
        generation.output_ok = False
        generation.output_error = {
            "code": retrieval.failure_type or "retriever_disabled",
            "message": retrieval.disabled_reason or "RAG retriever disabled",
            "details": {},
        }
        status_code = 503
    else:
        answer_execution = await execute_answer_generation(
            query=payload.query,
            documents=retrieval.documents,
            temporal_state=retrieval.temporal_state,
            generate_enabled=generate_enabled,
            trace_id=trace_id,
            run_generate=_run_generate_chat,
        )
        generation = answer_execution.generation
        contexts = answer_execution.contexts
        status_code = answer_execution.status_code

    latency_ms = _elapsed_ms(start_total)
    cache_state = CacheState(
        hit=retrieval.cache_hit if retrieval.rag_enabled else False,
        expires_at=retrieval.expires_at,
    )
    retrieved = [to_retrieved_document(doc) for doc in retrieval.documents]
    retriever_ready = retrieval.retriever_ready and retrieval.retrieval_failure is None
    _log_retrieval(
        request,
        "rag.answer",
        trace_id,
        rag_enabled=retrieval.rag_enabled,
        retriever_ready=retriever_ready,
        retrieval_doc_count=len(retrieval.documents),
        failure_type=retrieval.failure_type if status_code != 200 else None,
        index_path=retrieval.index_path,
        model_name=retrieval.model_name,
        retrieval_empty=retrieval.retrieval_empty,
        retrieval_empty_reason=retrieval.retrieval_empty_reason,
    )
    _log_retrieval(
        request,
        "llm.egress_decision",
        trace_id,
        **{k: v for k, v in generation.egress_decision.to_dict().items() if k != "trace_id"},
    )
    latency_event = {
        "t_total_ms": latency_ms,
        "t_retrieve_ms": retrieval.t_retrieve_ms,
        "t_cache_ms": retrieval.t_cache_ms,
        "t_prompt_ms": generation.t_prompt_ms,
        "t_llm_ms": generation.t_llm_ms,
        "t_parse_ms": generation.t_parse_ms,
        "rag_enabled": retrieval.rag_enabled,
        "retriever_ready": retriever_ready,
        "retrieved_count": len(retrieval.documents),
        "retrieval_empty": retrieval.retrieval_empty,
        "retrieval_empty_reason": retrieval.retrieval_empty_reason,
    }
    if generation.llm_attempted:
        latency_event["provider"] = generation.provider_label
        latency_event["model"] = generation.model_label
    _log_retrieval(request, "rag.answer.latency", trace_id, **latency_event)
    response = RagGeneratedResponse(
        trace_id=trace_id,
        latency_ms=latency_ms,
        question=payload.query,
        answer=generation.answer_text,
        contexts=contexts,
        retrieved=retrieved,
        model=generation.model_label,
        provider=generation.provider_label,
        rag_enabled=retrieval.rag_enabled,
        llm_enabled=generation.llm_enabled,
        disabled_reason=generation.disabled_reason,
        cache=cache_state,
        retrieval_empty=retrieval.retrieval_empty,
        retrieval_empty_reason=retrieval.retrieval_empty_reason,
        output_ok=generation.output_ok,
        output_error=generation.output_error,
        raw_answer=generation.raw_answer,
        label=generation.label,
        justification=generation.justification,
        citations=generation.citations or [],
        evidence_okay=generation.evidence_okay,
        assumptions=generation.assumptions or [],
        egress=generation.egress_decision.to_dict(),
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )


__all__ = ["router"]
