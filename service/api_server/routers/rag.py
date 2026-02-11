from __future__ import annotations

import json
import logging
import math
import time
import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from ..fuseki import FusekiGateway
from api_clients.llm_client import LLMProviderError, generate_chat
from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.rag import pipeline as rag_pipeline
from earCrawler.rag.output_schema import (
    DEFAULT_ALLOWED_LABELS,
    OutputSchemaError,
    make_unanswerable_payload,
    validate_and_extract_strict_answer,
)
from earCrawler.security.data_egress import (
    build_data_egress_decision,
    redact_contexts,
    redact_text_for_mode,
    resolve_redaction_mode,
)
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
from ..rag_support import RagQueryCache, RetrieverProtocol
from earCrawler.rag.retriever import RetrieverError

logger = logging.getLogger(__name__)
from .dependencies import (
    get_gateway,
    get_rag_cache,
    get_retriever,
    rate_limit,
)

router = APIRouter(prefix="/v1", tags=["rag"])

def _env_truthy(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int, min_value: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return max(min_value, value)


def _env_float(name: str, *, default: float, min_value: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    return max(min_value, value)


def _max_score(documents: list[dict]) -> float:
    best = 0.0
    for doc in documents or []:
        score = doc.get("score")
        if isinstance(score, (int, float)):
            best = max(best, float(score))
        elif isinstance(score, str):
            try:
                best = max(best, float(score))
            except ValueError:
                continue
    return best


def _log_retrieval(request: Request, event: str, trace_id: str, **details) -> None:
    request_logger = getattr(request.app.state, "request_logger", None)
    if request_logger:
        request_logger.info(event, trace_id=trace_id, details=details)
    else:  # pragma: no cover - fallback for tests
        logger.info("%s %s", event, details)


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


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
    cache_key = payload.cache_key()
    trace_id = getattr(request.state, "trace_id", "")
    rag_enabled = bool(getattr(retriever, "enabled", True))
    retriever_ready = bool(getattr(retriever, "ready", True))
    failure_type = getattr(retriever, "failure_type", None)
    index_path = getattr(retriever, "index_path", None)
    model_name = getattr(retriever, "model_name", None)
    t_cache_ms = 0.0
    t_retrieve_ms = 0.0
    t_prompt_ms = 0.0
    t_llm_ms = 0.0
    t_parse_ms = 0.0

    if not rag_enabled:
        disabled_reason = getattr(
            retriever,
            "disabled_reason",
            "RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1",
        )
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/retrieval",
            title="Retriever disabled",
            status=503,
            detail=disabled_reason,
            instance=str(request.url),
            trace_id=trace_id,
        )
        _log_retrieval(
            request,
            "rag.query.disabled",
            trace_id,
            rag_enabled=rag_enabled,
            retriever_ready=retriever_ready,
            retrieval_doc_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=failure_type or "retriever_disabled",
            failure_type=failure_type or "retriever_disabled",
            index_path=index_path,
            model_name=model_name,
        )
        _log_retrieval(
            request,
            "rag.query.latency",
            trace_id,
            t_total_ms=_elapsed_ms(start_total),
            t_retrieve_ms=t_retrieve_ms,
            t_cache_ms=t_cache_ms,
            t_prompt_ms=t_prompt_ms,
            t_llm_ms=t_llm_ms,
            t_parse_ms=t_parse_ms,
            rag_enabled=rag_enabled,
            retriever_ready=retriever_ready,
            retrieved_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=failure_type or "retriever_disabled",
        )
        return JSONResponse(
            status_code=503, content=problem.model_dump(exclude_none=True)
        )

    cache_start = time.perf_counter()
    cached = cache.get(cache_key)
    cache_hit = cached is not None
    t_cache_ms += _elapsed_ms(cache_start)
    documents: list[dict] = []
    expires_at = None
    retrieval_failure: Exception | None = None
    if cache_hit:
        cache_start = time.perf_counter()
        documents = cached or []
        expires_at = cache.expires_at(cache_key)
        t_cache_ms += _elapsed_ms(cache_start)
    else:
        retrieve_start = time.perf_counter()
        try:
            documents = retriever.query(payload.query, k=payload.top_k)
            t_retrieve_ms += _elapsed_ms(retrieve_start)
            cache_start = time.perf_counter()
            expires_at = cache.put(cache_key, documents)
            t_cache_ms += _elapsed_ms(cache_start)
        except RetrieverError as exc:
            t_retrieve_ms += _elapsed_ms(retrieve_start)
            retrieval_failure = exc
            failure_type = getattr(exc, "code", "retriever_error")
        except Exception as exc:  # pragma: no cover - defensive
            t_retrieve_ms += _elapsed_ms(retrieve_start)
            retrieval_failure = exc
            failure_type = failure_type or "retriever_error"

    if retrieval_failure:
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/retrieval",
            title="Retriever unavailable",
            status=503,
            detail=str(retrieval_failure),
            instance=str(request.url),
            trace_id=trace_id,
        )
        _log_retrieval(
            request,
            "rag.query.failed",
            trace_id,
            rag_enabled=rag_enabled,
            retriever_ready=retriever_ready,
            retrieval_doc_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=failure_type,
            failure_type=failure_type,
            index_path=index_path,
            model_name=model_name,
        )
        _log_retrieval(
            request,
            "rag.query.latency",
            trace_id,
            t_total_ms=_elapsed_ms(start_total),
            t_retrieve_ms=t_retrieve_ms,
            t_cache_ms=t_cache_ms,
            t_prompt_ms=t_prompt_ms,
            t_llm_ms=t_llm_ms,
            t_parse_ms=t_parse_ms,
            rag_enabled=rag_enabled,
            retriever_ready=retriever_ready,
            retrieved_count=0,
            retrieval_empty=True,
            retrieval_empty_reason=failure_type,
        )
        return JSONResponse(
            status_code=503, content=problem.model_dump(exclude_none=True)
        )

    results = []
    for doc in documents:
        result = await _build_answer(doc, gateway, payload.include_lineage)
        results.append(result)

    latency_ms = _elapsed_ms(start_total)
    cache_state = CacheState(hit=cache_hit, expires_at=expires_at)
    retrieval_empty = len(documents) == 0
    retrieval_empty_reason = "no_hits" if retrieval_empty else None
    _log_retrieval(
        request,
        "rag.query.success",
        trace_id,
        rag_enabled=rag_enabled,
        retriever_ready=retriever_ready,
        retrieval_doc_count=len(documents),
        retrieval_empty=retrieval_empty,
        retrieval_empty_reason=retrieval_empty_reason,
        failure_type=failure_type,
        index_path=index_path,
        model_name=model_name,
    )
    _log_retrieval(
        request,
        "rag.query.latency",
        trace_id,
        t_total_ms=latency_ms,
        t_retrieve_ms=t_retrieve_ms,
        t_cache_ms=t_cache_ms,
        t_prompt_ms=t_prompt_ms,
        t_llm_ms=t_llm_ms,
        t_parse_ms=t_parse_ms,
        rag_enabled=rag_enabled,
        retriever_ready=retriever_ready,
        retrieved_count=len(documents),
        retrieval_empty=retrieval_empty,
        retrieval_empty_reason=retrieval_empty_reason,
    )
    return RagResponse(
        trace_id=trace_id,
        latency_ms=latency_ms,
        query=payload.query,
        cache=cache_state,
        results=results,
        retrieval_empty=retrieval_empty,
        retrieval_empty_reason=retrieval_empty_reason,
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
    cache_key = payload.cache_key()
    generate_enabled = payload.generate if generate is None else bool(generate)
    rag_enabled = bool(getattr(retriever, "enabled", True))
    retriever_ready = bool(getattr(retriever, "ready", True))
    failure_type = getattr(retriever, "failure_type", None)
    index_path = getattr(retriever, "index_path", None)
    model_name = getattr(retriever, "model_name", None)
    redaction_mode = resolve_redaction_mode()
    t_cache_ms = 0.0
    t_retrieve_ms = 0.0
    t_prompt_ms = 0.0
    t_llm_ms = 0.0
    t_parse_ms = 0.0

    documents: list[dict] = []
    cache_hit = False
    expires_at = None
    disabled_reason = None
    retrieval_empty = False
    retrieval_empty_reason: str | None = None
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
        else:
            retrieve_start = time.perf_counter()
            try:
                documents = retriever.query(payload.query, k=payload.top_k)
                t_retrieve_ms += _elapsed_ms(retrieve_start)
                cache_start = time.perf_counter()
                expires_at = cache.put(cache_key, documents)
                t_cache_ms += _elapsed_ms(cache_start)
            except RetrieverError as exc:
                t_retrieve_ms += _elapsed_ms(retrieve_start)
                retrieval_failure = exc
                failure_type = getattr(exc, "code", "retriever_error")
            except Exception as exc:  # pragma: no cover - defensive
                t_retrieve_ms += _elapsed_ms(retrieve_start)
                retrieval_failure = exc
                failure_type = failure_type or "retriever_error"
    elif not rag_enabled:
        disabled_reason = getattr(
            retriever,
            "disabled_reason",
            "RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1",
        )
        retrieval_empty = True
        retrieval_empty_reason = failure_type or "retriever_disabled"
    else:
        retrieval_failure = getattr(
            retriever, "failure", RuntimeError("Retriever not ready")
        )
        failure_type = failure_type or "retriever_not_ready"

    contexts: list[str] = []
    answer: str | None = None
    status_code = 200
    model_label = None
    provider_label = None
    llm_enabled = False
    output_ok = False
    output_error: dict | None = None
    raw_answer: str | None = None
    label: str | None = None
    justification: str | None = None
    citations: list[dict] = []
    evidence_okay: dict | None = None
    assumptions: list[str] = []
    remote_attempted = False
    redacted_question = redact_text_for_mode(payload.query, mode=redaction_mode)
    egress_decision = build_data_egress_decision(
        remote_enabled=False,
        disabled_reason="generation not attempted",
        provider=None,
        model=None,
        redaction_mode=redaction_mode,
        question=redacted_question,
        contexts=[],
        messages=None,
        trace_id=trace_id,
    )

    if retrieval_failure:
        disabled_reason = str(retrieval_failure)
        retrieval_empty = True
        retrieval_empty_reason = failure_type or "retriever_error"
        status_code = 503
        output_error = {
            "code": failure_type or "retriever_error",
            "message": str(retrieval_failure),
            "details": {},
        }
        egress_decision = build_data_egress_decision(
            remote_enabled=False,
            disabled_reason=disabled_reason,
            provider=None,
            model=None,
            redaction_mode=redaction_mode,
            question=redacted_question,
            contexts=[],
            messages=None,
            trace_id=trace_id,
        )
    elif not rag_enabled:
        status_code = 503
        output_error = {
            "code": failure_type or "retriever_disabled",
            "message": disabled_reason or "RAG retriever disabled",
            "details": {},
        }
        egress_decision = build_data_egress_decision(
            remote_enabled=False,
            disabled_reason=disabled_reason or "RAG retriever disabled",
            provider=None,
            model=None,
            redaction_mode=redaction_mode,
            question=redacted_question,
            contexts=[],
            messages=None,
            trace_id=trace_id,
        )
    else:
        retrieval_empty = len(documents) == 0
        retrieval_empty_reason = (
            retrieval_empty_reason or ("no_hits" if retrieval_empty else None)
        )
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

        if not generate_enabled:
            llm_enabled = False
            output_ok = True
            disabled_reason = "generation_disabled_by_request"
            egress_decision = build_data_egress_decision(
                remote_enabled=False,
                disabled_reason=disabled_reason,
                provider=None,
                model=None,
                redaction_mode=redaction_mode,
                question=redacted_question,
                contexts=[],
                messages=None,
                trace_id=trace_id,
            )
        else:
            refuse_on_thin = _env_truthy("EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL", default=False)
            min_docs = _env_int("EARCRAWLER_THIN_RETRIEVAL_MIN_DOCS", default=1, min_value=1)
            min_top_score = _env_float("EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE", default=0.0, min_value=0.0)
            min_total_chars = _env_int("EARCRAWLER_THIN_RETRIEVAL_MIN_TOTAL_CHARS", default=0, min_value=0)

            thin_retrieval = retrieval_empty
            if not thin_retrieval and refuse_on_thin:
                if len(documents) < min_docs:
                    thin_retrieval = True
                elif _max_score(documents) < min_top_score:
                    thin_retrieval = True
                else:
                    total_chars = sum(len(str(c or "")) for c in prompt_contexts)
                    if total_chars < min_total_chars:
                        thin_retrieval = True

            if thin_retrieval:
                disabled_reason = "insufficient_evidence"
                llm_enabled = False
                output_ok = True

                prompt_start = time.perf_counter()
                redacted_contexts = redact_contexts(prompt_contexts, mode=redaction_mode)
                prompt = rag_pipeline._build_prompt(
                    redacted_question, redacted_contexts, label_schema=None
                )
                t_prompt_ms += _elapsed_ms(prompt_start)
                egress_decision = build_data_egress_decision(
                    remote_enabled=False,
                    disabled_reason=disabled_reason,
                    provider=None,
                    model=None,
                    redaction_mode=redaction_mode,
                    question=redacted_question,
                    contexts=redacted_contexts,
                    messages=prompt,
                    trace_id=trace_id,
                )

                refusal = make_unanswerable_payload(
                    hint="the relevant EAR excerpt(s) for this scenario (for example: ECCN, destination, end user/end use)",
                    justification="Retrieval evidence was empty or too thin to ground a compliant answer.",
                    evidence_reasons=["thin_or_empty_retrieval"],
                )
                rendered = json.dumps(refusal, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                validated = validate_and_extract_strict_answer(
                    rendered,
                    allowed_labels=DEFAULT_ALLOWED_LABELS,
                    context="\n\n".join(redacted_contexts),
                )
                answer = str(validated["answer_text"])
                label = str(validated["label"])
                citations = list(validated.get("citations") or [])
                assumptions = list(validated.get("assumptions") or [])
                evidence_okay = dict(validated.get("evidence_okay") or {})
                justification = validated.get("justification")
            else:
                llm_start: float | None = None
                parse_start: float | None = None
                try:
                    cfg = get_llm_config()
                    provider_label = cfg.provider.provider
                    model_label = cfg.provider.model
                    prompt_start = time.perf_counter()
                    redacted_contexts = redact_contexts(prompt_contexts, mode=redaction_mode)
                    prompt = rag_pipeline._build_prompt(
                        redacted_question, redacted_contexts, label_schema=None
                    )
                    t_prompt_ms += _elapsed_ms(prompt_start)
                    if not cfg.enable_remote:
                        disabled_reason = (
                            cfg.remote_disabled_reason
                            or "remote LLM policy denied egress"
                        )
                        llm_enabled = False
                        status_code = 503
                        output_error = {
                            "code": "llm_disabled",
                            "message": disabled_reason,
                            "details": {},
                        }
                        egress_decision = build_data_egress_decision(
                            remote_enabled=False,
                            disabled_reason=disabled_reason,
                            provider=provider_label,
                            model=model_label,
                            redaction_mode=redaction_mode,
                            question=redacted_question,
                            contexts=redacted_contexts,
                            messages=prompt,
                            trace_id=trace_id,
                        )
                    else:
                        remote_attempted = True
                        llm_start = time.perf_counter()
                        raw_answer = generate_chat(
                            prompt,
                            provider=provider_label,
                            model=model_label,
                        )
                        t_llm_ms += _elapsed_ms(llm_start)
                        llm_enabled = True
                        egress_decision = build_data_egress_decision(
                            remote_enabled=True,
                            disabled_reason=None,
                            provider=provider_label,
                            model=model_label,
                            redaction_mode=redaction_mode,
                            question=redacted_question,
                            contexts=redacted_contexts,
                            messages=prompt,
                            trace_id=trace_id,
                        )
                        parse_start = time.perf_counter()
                        validated = validate_and_extract_strict_answer(
                            raw_answer,
                        allowed_labels=DEFAULT_ALLOWED_LABELS,
                        context="\n\n".join(redacted_contexts),
                    )
                    t_parse_ms += _elapsed_ms(parse_start)
                    output_ok = True
                    answer = str(validated["answer_text"])
                    label = str(validated["label"])
                    citations = list(validated.get("citations") or [])
                    assumptions = list(validated.get("assumptions") or [])
                    evidence_okay = dict(validated.get("evidence_okay") or {})
                    justification = validated.get("justification")
                except LLMProviderError as exc:
                    if llm_start is not None:
                        t_llm_ms += _elapsed_ms(llm_start)
                    disabled_reason = str(exc)
                    llm_enabled = False
                    status_code = 503
                    output_error = {
                        "code": "llm_unavailable",
                        "message": str(exc),
                        "details": {},
                    }
                    egress_decision = build_data_egress_decision(
                        remote_enabled=remote_attempted,
                        disabled_reason=str(exc),
                        provider=provider_label,
                        model=model_label,
                        redaction_mode=redaction_mode,
                        question=redacted_question,
                        contexts=redact_contexts(contexts, mode=redaction_mode),
                        messages=None,
                        trace_id=trace_id,
                    )
                except OutputSchemaError as exc:
                    if parse_start is not None:
                        t_parse_ms += _elapsed_ms(parse_start)
                    output_ok = False
                    output_error = exc.as_dict()
                    failure_type = exc.code
                    status_code = 422
                    answer = None
                    label = None
                    justification = None
                    citations = []
                    assumptions = []
                    evidence_okay = None
                except Exception as exc:  # pragma: no cover - defensive
                    disabled_reason = str(exc)
                    llm_enabled = False
                    status_code = 503
                    output_error = {
                        "code": "llm_unavailable",
                        "message": str(exc),
                        "details": {},
                    }
                    egress_decision = build_data_egress_decision(
                        remote_enabled=remote_attempted,
                        disabled_reason=str(exc),
                        provider=provider_label,
                        model=model_label,
                        redaction_mode=redaction_mode,
                        question=redacted_question,
                        contexts=redact_contexts(contexts, mode=redaction_mode),
                        messages=None,
                        trace_id=trace_id,
                    )

    latency_ms = _elapsed_ms(start_total)
    cache_state = CacheState(
        hit=cache_hit if rag_enabled else False, expires_at=expires_at
    )
    retrieved = [_to_retrieved_document(doc) for doc in documents]
    _log_retrieval(
        request,
        "rag.answer",
        trace_id,
        rag_enabled=rag_enabled,
        retriever_ready=retriever_ready and retrieval_failure is None,
        retrieval_doc_count=len(documents),
        failure_type=failure_type if status_code != 200 else None,
        index_path=index_path,
        model_name=model_name,
        retrieval_empty=retrieval_empty,
        retrieval_empty_reason=retrieval_empty_reason,
    )
    _log_retrieval(
        request,
        "llm.egress_decision",
        trace_id,
        **{k: v for k, v in egress_decision.to_dict().items() if k != "trace_id"},
    )
    latency_event = {
        "t_total_ms": latency_ms,
        "t_retrieve_ms": t_retrieve_ms,
        "t_cache_ms": t_cache_ms,
        "t_prompt_ms": t_prompt_ms,
        "t_llm_ms": t_llm_ms,
        "t_parse_ms": t_parse_ms,
        "rag_enabled": rag_enabled,
        "retriever_ready": retriever_ready and retrieval_failure is None,
        "retrieved_count": len(documents),
        "retrieval_empty": retrieval_empty,
        "retrieval_empty_reason": retrieval_empty_reason,
    }
    if remote_attempted:
        latency_event["provider"] = provider_label
        latency_event["model"] = model_label
    _log_retrieval(request, "rag.answer.latency", trace_id, **latency_event)
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
        retrieval_empty=retrieval_empty,
        retrieval_empty_reason=retrieval_empty_reason,
        output_ok=output_ok,
        output_error=output_error,
        raw_answer=raw_answer,
        label=label,
        justification=justification,
        citations=citations,
        evidence_okay=evidence_okay,
        assumptions=assumptions,
        egress=egress_decision.to_dict(),
    )
    return JSONResponse(
        status_code=status_code, content=response.model_dump(mode="json")
    )


__all__ = ["router"]
