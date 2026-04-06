from __future__ import annotations

"""RAG route orchestration helpers."""

import asyncio
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Mapping

from earCrawler.rag import llm_runtime, orchestrator, retrieval_runtime

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
GenerateRunner = orchestrator.GenerateRunner


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


@dataclass(frozen=True)
class PromptContextBudget:
    max_contexts: int | None
    max_context_chars: int | None
    max_total_chars: int | None
    dedupe: bool


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


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _env_optional_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _resolve_prompt_context_budget() -> PromptContextBudget:
    provider = str(os.getenv("LLM_PROVIDER") or "").strip().lower()
    max_contexts = _env_optional_int("EARCRAWLER_RAG_PROMPT_MAX_CONTEXTS")
    max_context_chars = _env_optional_int("EARCRAWLER_RAG_PROMPT_MAX_CONTEXT_CHARS")
    max_total_chars = _env_optional_int("EARCRAWLER_RAG_PROMPT_MAX_TOTAL_CHARS")
    dedupe = _env_optional_bool("EARCRAWLER_RAG_PROMPT_DEDUP")

    if provider == "local_adapter":
        if max_contexts is None:
            max_contexts = 3
        if max_context_chars is None:
            max_context_chars = 1200
        if max_total_chars is None:
            max_total_chars = 3600
        if dedupe is None:
            dedupe = True
    elif dedupe is None:
        dedupe = False

    return PromptContextBudget(
        max_contexts=max_contexts,
        max_context_chars=max_context_chars,
        max_total_chars=max_total_chars,
        dedupe=bool(dedupe),
    )


def _truncate_prompt_context(text: str, *, limit: int) -> str:
    value = str(text or "").strip()
    if not value or limit <= 0 or len(value) <= limit:
        return value
    suffix = " [truncated]"
    if limit <= len(suffix):
        return value[:limit].rstrip()
    clipped = value[: limit - len(suffix)].rstrip()
    split_at = clipped.rfind(" ")
    if split_at >= max(0, len(clipped) // 2):
        clipped = clipped[:split_at].rstrip()
    if not clipped:
        clipped = value[: limit - len(suffix)].rstrip()
    return f"{clipped}{suffix}"


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
    temporal_state: dict[str, object] = {
        "requested": bool(effective_date),
        "effective_date": effective_date,
    }
    warnings: list[dict[str, object]] = []

    t_cache_ms = 0.0
    t_retrieve_ms = 0.0
    documents: list[dict] = []
    cache_hit = False
    expires_at = None
    retrieval_failure: Exception | None = None

    retriever_state = orchestrator.resolve_retriever_state(retriever=retriever)
    rag_enabled = retriever_state.rag_enabled
    retriever_ready = retriever_state.retriever_ready
    failure_type = retriever_state.failure_type
    disabled_reason = retriever_state.disabled_reason
    index_path = retriever_state.index_path
    model_name = retriever_state.model_name

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
        else:
            try:
                retrieval_execution = await asyncio.to_thread(
                    orchestrator.run_retrieval_sync,
                    query=query,
                    top_k=top_k,
                    retriever=retriever,
                    strict=True,
                    effective_date=effective_date,
                )
                documents = retrieval_execution.docs
                warnings = retrieval_execution.warnings
                temporal_state = retrieval_execution.temporal_state
                t_retrieve_ms += retrieval_execution.t_retrieve_ms
                if (not bool(temporal_state.get("requested"))) or documents:
                    cache_start = time.perf_counter()
                    expires_at = cache.put(cache_key, documents)
                    t_cache_ms += _elapsed_ms(cache_start)
            except Exception as exc:
                retrieval_failure = exc
                failure_type = getattr(exc, "code", failure_type or "retriever_error")
    else:
        retrieval_failure = getattr(retriever, "failure", RuntimeError("Retriever not ready"))
        failure_type = failure_type or "retriever_not_ready"

    retriever_state = orchestrator.resolve_retriever_state(
        retriever=retriever,
        warnings=warnings,
        retrieval_failure=retrieval_failure,
    )
    rag_enabled = retriever_state.rag_enabled
    retriever_ready = retriever_state.retriever_ready
    failure_type = retriever_state.failure_type
    disabled_reason = retriever_state.disabled_reason
    index_path = retriever_state.index_path
    model_name = retriever_state.model_name
    retrieval_empty, retrieval_empty_reason = orchestrator.resolve_retrieval_empty_state(
        docs=documents,
        temporal_state=temporal_state,
        retriever_state=retriever_state,
        retrieval_failure=retrieval_failure,
        warnings=warnings,
        prefer_warning_reason=False,
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
    summary = retrieval_runtime.summarize_retrieved_doc(doc, source="retrieval")
    raw = doc.get("raw") if isinstance(doc.get("raw"), Mapping) else {}
    raw = raw or {}
    score = _coerce_score(doc.get("score"))
    source = RagSource(
        id=_maybe_str(summary.get("id")),
        url=_maybe_str(summary.get("url")),
        label=_maybe_str(summary.get("title")),
        section=_maybe_str(raw.get("section")) or _maybe_str(summary.get("section")),
        provider=_maybe_str(raw.get("provider")) or _maybe_str(doc.get("provider")),
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
    budget = _resolve_prompt_context_budget()
    contexts: list[str] = []
    seen: set[str] = set()
    total_chars = 0
    for doc in documents:
        text = retrieval_runtime.extract_text(doc)
        if not text:
            continue
        raw = doc.get("raw") if isinstance(doc.get("raw"), Mapping) else {}
        raw = raw or {}
        section = (
            _maybe_str(raw.get("section"))
            or _maybe_str(doc.get("section"))
            or _maybe_str(doc.get("span_id"))
            or _maybe_str(doc.get("doc_id"))
            or _maybe_str(doc.get("id"))
            or _maybe_str(doc.get("entity_id"))
            or _maybe_str(doc.get("section_id"))
        )
        if budget.max_contexts is not None and len(contexts) >= budget.max_contexts:
            break
        if section:
            context = f"[{section}] {text}"
        else:
            context = text
        if budget.dedupe:
            if context in seen:
                continue
            seen.add(context)
        char_limit = budget.max_context_chars
        if budget.max_total_chars is not None:
            remaining_chars = budget.max_total_chars - total_chars
            if remaining_chars <= 0:
                break
            char_limit = (
                remaining_chars
                if char_limit is None
                else min(char_limit, remaining_chars)
            )
        if char_limit is not None:
            context = _truncate_prompt_context(context, limit=char_limit)
        if not context:
            continue
        contexts.append(context)
        total_chars += len(context)
    return contexts


def to_retrieved_document(doc: dict) -> RetrievedDocument:
    summary = retrieval_runtime.summarize_retrieved_doc(doc, source="retrieval")
    raw = doc.get("raw") if isinstance(doc.get("raw"), Mapping) else {}
    raw = raw or {}
    return RetrievedDocument(
        id=_maybe_str(summary.get("id")),
        score=_coerce_score(doc.get("score")),
        title=_maybe_str(summary.get("title")),
        url=_maybe_str(summary.get("url")),
        section=_maybe_str(raw.get("section")) or _maybe_str(summary.get("section")),
        provider=_maybe_str(raw.get("provider")) or _maybe_str(doc.get("provider")),
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
    generation = await orchestrator.execute_generation_async(
        request=orchestrator.RagRequest(
            question=query,
            generate=generate_enabled,
            strict_output=True,
            trace_id=trace_id,
            effective_date=str(temporal_state.get("effective_date") or "").strip() or None,
            refuse_on_empty=True,
            empty_collections_on_error=True,
        ),
        docs=documents,
        contexts=contexts,
        temporal_state=temporal_state,
        run_generate=run_generate,
    )
    return ApiAnswerExecution(
        status_code=orchestrator.generation_status_code(generation),
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
