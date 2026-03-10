from __future__ import annotations

"""RAG route orchestration helpers."""

import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from api_clients.llm_client import LLMProviderError
from earCrawler.rag import llm_runtime, policy, retrieval_runtime
from earCrawler.rag.temporal import (
    resolve_temporal_request,
    select_temporal_documents,
    temporal_candidate_count,
)

from .fuseki import FusekiGateway
from .rag_support import RagQueryCache, RetrieverProtocol
from .schemas import (
    LineageEdge,
    RagAnswer,
    RagLineageReference,
    RagSource,
    RetrievedDocument,
)


QueryRunner = Callable[[RetrieverProtocol, str, int], Awaitable[list[dict]]]
GenerateRunner = Callable[[list[dict[str, str]] | list[dict], str, str], Awaitable[str]]


@dataclass
class ApiRetrievalResult:
    documents: list[dict]
    cache_hit: bool
    expires_at: datetime | None
    temporal_state: dict[str, object]
    rag_enabled: bool
    retriever_ready: bool
    failure_type: str | None
    disabled_reason: str | None
    retrieval_failure: Exception | None
    retrieval_empty: bool
    retrieval_empty_reason: str | None
    t_cache_ms: float
    t_retrieve_ms: float
    index_path: str | None
    model_name: str | None


@dataclass
class ApiAnswerExecution:
    status_code: int
    contexts: list[str]
    generation: llm_runtime.GenerationResult


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


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


async def retrieve_documents(
    *,
    query: str,
    top_k: int,
    effective_date: str | None,
    cache_key: str,
    retriever: RetrieverProtocol,
    cache: RagQueryCache,
    run_query: QueryRunner,
) -> ApiRetrievalResult:
    rag_enabled = bool(getattr(retriever, "enabled", True))
    retriever_ready = bool(getattr(retriever, "ready", True))
    failure_type = getattr(retriever, "failure_type", None)
    index_path = getattr(retriever, "index_path", None)
    model_name = getattr(retriever, "model_name", None)
    temporal_request = resolve_temporal_request(query, effective_date=effective_date)
    temporal_state = (
        select_temporal_documents([], request=temporal_request, top_k=top_k).to_dict()
        if temporal_request.refusal_reason
        else temporal_request.to_dict()
    )

    t_cache_ms = 0.0
    t_retrieve_ms = 0.0
    documents: list[dict] = []
    cache_hit = False
    expires_at = None
    disabled_reason: str | None = None
    retrieval_failure: Exception | None = None

    if rag_enabled and retriever_ready:
        cache_start = time.perf_counter()
        cached = cache.get(cache_key)
        cache_hit = cached is not None
        t_cache_ms += _elapsed_ms(cache_start)
        if cache_hit:
            cache_start = time.perf_counter()
            documents = cached or []
            expires_at = cache.expires_at(cache_key)
            t_cache_ms += _elapsed_ms(cache_start)
        elif temporal_request.refusal_reason:
            documents = []
        else:
            retrieve_start = time.perf_counter()
            try:
                documents = await run_query(
                    retriever,
                    query,
                    temporal_candidate_count(top_k) if temporal_request.requested else top_k,
                )
                if temporal_request.requested:
                    selection = select_temporal_documents(
                        documents,
                        request=temporal_request,
                        top_k=top_k,
                    )
                    temporal_state = selection.to_dict()
                    documents = list(selection.selected_docs)
                t_retrieve_ms += _elapsed_ms(retrieve_start)
                if (not temporal_request.requested) or documents:
                    cache_start = time.perf_counter()
                    expires_at = cache.put(cache_key, documents)
                    t_cache_ms += _elapsed_ms(cache_start)
            except Exception as exc:
                t_retrieve_ms += _elapsed_ms(retrieve_start)
                retrieval_failure = exc
                failure_type = getattr(exc, "code", failure_type or "retriever_error")
    elif not rag_enabled:
        disabled_reason = getattr(
            retriever,
            "disabled_reason",
            "RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1",
        )
    else:
        retrieval_failure = getattr(retriever, "failure", RuntimeError("Retriever not ready"))
        failure_type = failure_type or "retriever_not_ready"

    if not rag_enabled:
        retrieval_empty = True
        retrieval_empty_reason = failure_type or "retriever_disabled"
    elif retrieval_failure is not None:
        retrieval_empty = True
        retrieval_empty_reason = failure_type or "retriever_error"
    else:
        retrieval_empty = len(documents) == 0
        retrieval_empty_reason = (
            (str(temporal_state.get("refusal_reason") or "").strip() or "no_temporally_applicable_evidence")
            if retrieval_empty and temporal_request.requested
            else ("no_hits" if retrieval_empty else None)
        )

    return ApiRetrievalResult(
        documents=documents,
        cache_hit=cache_hit,
        expires_at=expires_at,
        temporal_state=temporal_state,
        rag_enabled=rag_enabled,
        retriever_ready=retriever_ready,
        failure_type=failure_type,
        disabled_reason=disabled_reason,
        retrieval_failure=retrieval_failure,
        retrieval_empty=retrieval_empty,
        retrieval_empty_reason=retrieval_empty_reason,
        t_cache_ms=t_cache_ms,
        t_retrieve_ms=t_retrieve_ms,
        index_path=index_path,
        model_name=model_name,
    )


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


async def _build_query_answer(
    doc: dict,
    *,
    gateway: FusekiGateway,
    include_lineage: bool,
) -> RagAnswer:
    content = retrieval_runtime.extract_text(doc)
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


async def build_query_answers(
    documents: list[dict],
    *,
    gateway: FusekiGateway,
    include_lineage: bool,
) -> list[RagAnswer]:
    results: list[RagAnswer] = []
    for doc in documents:
        results.append(
            await _build_query_answer(
                doc,
                gateway=gateway,
                include_lineage=include_lineage,
            )
        )
    return results


def build_prompt_contexts(documents: list[dict]) -> list[str]:
    return retrieval_runtime.build_context_lines(
        documents,
        normalize_section_headers=False,
    )


def to_retrieved_document(doc: dict) -> RetrievedDocument:
    return RetrievedDocument(
        id=_maybe_str(doc.get("id") or doc.get("entity_id") or doc.get("section")),
        score=_coerce_score(doc.get("score")),
        title=_maybe_str(doc.get("title") or doc.get("label")),
        url=_maybe_str(doc.get("source_url") or doc.get("url")),
        section=_maybe_str(doc.get("section")),
        provider=_maybe_str(doc.get("provider")),
    )


def _provider_error_generation(
    *,
    code: str,
    message: str,
    egress_decision,
    provider_label: str | None,
    model_label: str | None,
    llm_attempted: bool,
    t_prompt_ms: float,
    t_llm_ms: float = 0.0,
) -> llm_runtime.GenerationResult:
    return llm_runtime.GenerationResult(
        provider_label=provider_label,
        model_label=model_label,
        llm_enabled=False,
        llm_attempted=llm_attempted,
        raw_answer=None,
        disabled_reason=message,
        output_ok=False,
        output_error={"code": code, "message": message, "details": {}},
        egress_decision=egress_decision,
        prompt=None,
        t_prompt_ms=t_prompt_ms,
        t_llm_ms=t_llm_ms,
    )


async def execute_answer_generation(
    *,
    query: str,
    documents: list[dict],
    temporal_state: dict[str, object],
    generate_enabled: bool,
    trace_id: str | None,
    run_generate: GenerateRunner,
) -> ApiAnswerExecution:
    contexts = build_prompt_contexts(documents)
    if not generate_enabled:
        return ApiAnswerExecution(
            status_code=200,
            contexts=contexts,
            generation=llm_runtime.build_generation_disabled_result(
                question=query,
                disabled_reason="generation_disabled_by_request",
                trace_id=trace_id,
            ),
        )

    prompt_start = time.perf_counter()
    prompt_artifacts = llm_runtime.build_prompt_artifacts(
        query,
        contexts,
        effective_date=str(temporal_state.get("effective_date") or "").strip() or None,
    )
    t_prompt_ms = _elapsed_ms(prompt_start)

    policy_decision = policy.evaluate_generation_policy(
        docs=documents,
        contexts=prompt_artifacts.redacted_contexts,
        temporal_state=temporal_state,
        refuse_on_empty=True,
    )
    if policy_decision.should_refuse:
        generation = llm_runtime.build_refusal_result(
            policy_decision.refusal_payload or {},
            prompt_artifacts=prompt_artifacts,
            disabled_reason=policy_decision.disabled_reason or "insufficient_evidence",
            trace_id=trace_id,
        )
        generation.t_prompt_ms = t_prompt_ms
        return ApiAnswerExecution(status_code=200, contexts=contexts, generation=generation)

    try:
        request = llm_runtime.resolve_llm_request(
            prompt_artifacts,
            trace_id=trace_id,
        )
    except llm_runtime.LLMExecutionError as exc:
        generation = _provider_error_generation(
            code=exc.error_code,
            message=exc.disabled_reason,
            egress_decision=exc.egress_decision,
            provider_label=exc.provider_label,
            model_label=exc.model_label,
            llm_attempted=False,
            t_prompt_ms=t_prompt_ms,
        )
        return ApiAnswerExecution(status_code=503, contexts=contexts, generation=generation)

    llm_start = time.perf_counter()
    try:
        raw_answer = await run_generate(
            prompt_artifacts.prompt,
            request.provider_label,
            request.model_label,
        )
    except LLMProviderError as exc:
        generation = _provider_error_generation(
            code="llm_unavailable",
            message=str(exc),
            egress_decision=request.build_egress_decision(
                remote_enabled=True,
                disabled_reason=str(exc),
                trace_id=trace_id,
            ),
            provider_label=request.provider_label,
            model_label=request.model_label,
            llm_attempted=True,
            t_prompt_ms=t_prompt_ms,
            t_llm_ms=_elapsed_ms(llm_start),
        )
        return ApiAnswerExecution(status_code=503, contexts=contexts, generation=generation)

    generation = llm_runtime.validate_generated_answer(
        str(raw_answer),
        prompt_artifacts=prompt_artifacts,
        provider_label=request.provider_label,
        model_label=request.model_label,
        egress_decision=request.build_egress_decision(
            remote_enabled=True,
            disabled_reason=None,
            trace_id=trace_id,
        ),
        strict_output=True,
        empty_collections_on_error=True,
    )
    generation.t_prompt_ms = t_prompt_ms
    generation.t_llm_ms = _elapsed_ms(llm_start)
    return ApiAnswerExecution(
        status_code=200 if generation.output_ok else 422,
        contexts=contexts,
        generation=generation,
    )


__all__ = [
    "ApiAnswerExecution",
    "ApiRetrievalResult",
    "build_prompt_contexts",
    "build_query_answers",
    "execute_answer_generation",
    "retrieve_documents",
    "to_retrieved_document",
]
