from __future__ import annotations

"""Thin RAG pipeline wrapper around the configured dense or hybrid retriever."""

import os
import time
from typing import Mapping

from api_clients.llm_client import generate_chat
from earCrawler.audit import required_events as audit_required_events
from earCrawler.rag import llm_runtime, orchestrator, retrieval_runtime
from earCrawler.utils.log_json import JsonLogger

_logger = JsonLogger("rag-pipeline")


def _ensure_retriever(
    retriever: object | None = None,
    *,
    strict: bool = True,
    warnings: list[dict[str, object]] | None = None,
):
    return retrieval_runtime.ensure_retriever(
        retriever,
        strict=strict,
        warnings=warnings,
        logger=_logger,
    )


def _normalize_section_id(value: object | None) -> str | None:
    return retrieval_runtime.normalize_section_id(value)


def retrieve_regulation_context(
    query: str,
    top_k: int = 5,
    *,
    retriever: object | None = None,
    strict: bool = True,
    warnings: list[dict[str, object]] | None = None,
    effective_date: str | None = None,
    temporal_state: dict[str, object] | None = None,
) -> list[dict]:
    return retrieval_runtime.retrieve_regulation_context(
        query,
        top_k=top_k,
        retriever=retriever,
        strict=strict,
        warnings=warnings,
        effective_date=effective_date,
        temporal_state=temporal_state,
        ensure_retriever_fn=_ensure_retriever,
        logger=_logger,
    )


def _kg_expansion_mode():
    return retrieval_runtime.kg_expansion_mode()



def _should_run_kg_expansion(*, task: str | None, explicit: bool | None) -> bool:
    return retrieval_runtime.should_run_kg_expansion(task=task, explicit=explicit)



def _create_fuseki_gateway():
    return retrieval_runtime.create_fuseki_gateway()



def expand_with_kg(
    section_ids,
    *,
    provider: str = "fuseki",
    gateway=None,
):
    return retrieval_runtime.expand_with_kg(
        section_ids,
        provider=provider,
        gateway=gateway,
        gateway_factory=_create_fuseki_gateway,
        logger=_logger,
    )



def answer_with_rag(
    question: str,
    *,
    task: str | None = None,
    label_schema: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    top_k: int = 5,
    retriever: object | None = None,
    kg_expansion: bool | None = None,
    strict_retrieval: bool = True,
    strict_output: bool = True,
    generate: bool = True,
    effective_date: str | None = None,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Run retrieval + optional KG expansion + LLM generation."""

    t_total_start = time.perf_counter()
    audit_run_id = str(run_id or os.getenv("EARCTL_AUDIT_RUN_ID") or "").strip() or None
    t_cache_ms = 0.0
    retrieval_warnings: list[dict[str, object]] = []
    temporal_state: dict[str, object] = {}
    retrieve_start = time.perf_counter()
    docs = retrieve_regulation_context(
        question,
        top_k=top_k,
        retriever=retriever,
        strict=strict_retrieval,
        warnings=retrieval_warnings,
        effective_date=effective_date,
        temporal_state=temporal_state,
    )
    t_retrieve_ms = round((time.perf_counter() - retrieve_start) * 1000.0, 3)

    retriever_state = orchestrator.resolve_retriever_state(
        retriever=retriever,
        warnings=retrieval_warnings,
    )
    rag_enabled = retriever_state.rag_enabled
    retriever_ready = retriever_state.retriever_ready
    retrieval_empty, retrieval_empty_reason = orchestrator.resolve_retrieval_empty_state(
        docs=docs,
        temporal_state=temporal_state,
        retriever_state=retriever_state,
        warnings=retrieval_warnings,
        prefer_warning_reason=True,
    )
    temporal_requested = bool(temporal_state.get("requested"))
    temporal_effective_date = str(temporal_state.get("effective_date") or "").strip() or None

    section_ids = [str(doc["section_id"]) for doc in docs if doc.get("section_id")]
    kg_mode = _kg_expansion_mode()
    kg_expansion_enabled = _should_run_kg_expansion(task=task, explicit=kg_expansion)
    _logger.info(
        "rag.kg_expansion.mode",
        mode=kg_mode,
        enabled=kg_expansion_enabled,
        task=str(task or ""),
        explicit=kg_expansion,
    )
    kg_snippets = expand_with_kg(section_ids) if kg_expansion_enabled else []
    context_bundle = retrieval_runtime.build_retrieval_context_bundle(
        docs,
        kg_expansion=kg_snippets,
    )

    request = orchestrator.RagRequest(
        question=question,
        top_k=top_k,
        effective_date=effective_date,
        task=task,
        label_schema=label_schema,
        provider=provider,
        model=model,
        generate=generate,
        strict_output=strict_output,
        trace_id=trace_id,
        refuse_on_empty=False,
        empty_collections_on_error=False,
    )
    try:
        generation = orchestrator.execute_generation_sync(
            request=request,
            docs=docs,
            contexts=context_bundle.contexts,
            temporal_state=temporal_state,
            raise_on_llm_error=True,
            generate_chat_fn=generate_chat,
        )
    except llm_runtime.LLMExecutionError as exc:
        _logger.info("llm.egress_decision", **exc.egress_decision.to_dict())
        _logger.error("rag.answer.failed", error=str(exc))
        raise

    t_prompt_ms = generation.t_prompt_ms
    t_llm_ms = generation.t_llm_ms
    t_parse_ms = generation.t_parse_ms
    if generation.egress_decision:
        _logger.info("llm.egress_decision", **generation.egress_decision.to_dict())

    t_total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 3)
    latency_fields: dict[str, object] = {
        "trace_id": trace_id,
        "t_total_ms": t_total_ms,
        "t_retrieve_ms": t_retrieve_ms,
        "t_cache_ms": t_cache_ms,
        "t_prompt_ms": t_prompt_ms,
        "t_llm_ms": t_llm_ms,
        "t_parse_ms": t_parse_ms,
        "rag_enabled": rag_enabled,
        "retriever_ready": retriever_ready,
        "retrieved_count": len(docs),
    }
    if generation.llm_attempted:
        latency_fields["provider"] = generation.provider_label
        latency_fields["model"] = generation.model_label
    _logger.info("rag.pipeline.latency", **latency_fields)

    try:
        audit_required_events.emit_remote_llm_policy_decision(
            trace_id=trace_id,
            run_id=audit_run_id,
            egress_decision=generation.egress_decision.to_dict() if generation.egress_decision else {},
        )
        output_error_code: str | None = None
        if isinstance(generation.output_error, Mapping):
            raw_code = generation.output_error.get("code")
            if raw_code is not None:
                output_error_code = str(raw_code)
        audit_required_events.emit_query_outcome(
            trace_id=trace_id,
            run_id=audit_run_id,
            label=generation.label,
            answer_text=generation.answer_text,
            output_ok=bool(generation.output_ok),
            retrieval_empty=bool(retrieval_empty),
            retrieval_empty_reason=str(retrieval_empty_reason or "") or None,
            disabled_reason=str(generation.disabled_reason or "") or None,
            output_error_code=output_error_code,
        )
    except Exception as exc:  # pragma: no cover - audit logging must never break answers
        _logger.warning("audit.event.emit_failed", error=str(exc), trace_id=trace_id)

    return {
        "question": question,
        "answer": generation.answer_text,
        "label": generation.label,
        "justification": generation.justification,
        "citations": generation.citations,
        "retrieved_docs": context_bundle.retrieved_docs,
        "kg_expansions": context_bundle.kg_expansions_payload,
        "kg_paths_used": context_bundle.kg_paths_payload,
        "trace_id": trace_id,
        "evidence_okay": generation.evidence_okay,
        "assumptions": generation.assumptions,
        "citation_span_ids": generation.citation_span_ids,
        "used_sections": context_bundle.section_ids,
        "contexts": context_bundle.contexts,
        "prompt_contexts": context_bundle.contexts,
        "rag_enabled": rag_enabled,
        "retriever_ready": retriever_ready,
        "llm_enabled": generation.llm_enabled,
        "disabled_reason": generation.disabled_reason,
        "raw_context": "\n\n".join(context_bundle.contexts),
        "raw_answer": generation.raw_answer,
        "retrieval_warnings": retrieval_warnings,
        "retrieval_empty": retrieval_empty,
        "retrieval_empty_reason": retrieval_empty_reason,
        "output_ok": generation.output_ok,
        "output_error": generation.output_error,
        "temporal_requested": temporal_requested,
        "effective_date": temporal_effective_date,
        "temporal_decision": temporal_state or None,
        "timings": {
            "t_total_ms": t_total_ms,
            "t_retrieve_ms": t_retrieve_ms,
            "t_cache_ms": t_cache_ms,
            "t_prompt_ms": t_prompt_ms,
            "t_llm_ms": t_llm_ms,
            "t_parse_ms": t_parse_ms,
        },
        "egress_decision": generation.egress_decision.to_dict() if generation.egress_decision else None,
    }


__all__ = [
    "answer_with_rag",
    "expand_with_kg",
    "retrieve_regulation_context",
]
