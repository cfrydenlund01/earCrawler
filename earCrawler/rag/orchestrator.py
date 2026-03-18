from __future__ import annotations

"""Shared orchestration helpers used by pipeline and API RAG adapters."""

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping, Protocol, Sequence

from api_clients.llm_client import LLMProviderError, generate_chat
from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.rag import llm_runtime, policy, retrieval_runtime


@dataclass(frozen=True)
class RagRequest:
    question: str
    top_k: int = 5
    effective_date: str | None = None
    task: str | None = None
    label_schema: str | None = None
    provider: str | None = None
    model: str | None = None
    generate: bool = True
    strict_output: bool = True
    trace_id: str | None = None
    refuse_on_empty: bool = True
    empty_collections_on_error: bool = True


@dataclass(frozen=True)
class RetrieverState:
    rag_enabled: bool
    retriever_ready: bool
    failure_type: str | None
    disabled_reason: str | None
    index_path: str | None
    model_name: str | None


@dataclass
class RetrievalExecution:
    docs: list[dict]
    warnings: list[dict[str, object]]
    temporal_state: dict[str, object]
    t_retrieve_ms: float


class GenerateRunner(Protocol):
    def __call__(
        self,
        prompt: list[dict[str, str]] | list[dict],
        provider: str,
        model: str,
    ) -> Awaitable[str]: ...


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


def _maybe_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def run_retrieval_sync(
    *,
    query: str,
    top_k: int,
    retriever: object | None,
    strict: bool,
    effective_date: str | None,
    ensure_retriever_fn=None,
) -> RetrievalExecution:
    warnings: list[dict[str, object]] = []
    temporal_state: dict[str, object] = {}
    retrieve_start = time.perf_counter()
    docs = retrieval_runtime.retrieve_regulation_context(
        query,
        top_k=top_k,
        retriever=retriever,
        strict=strict,
        warnings=warnings,
        effective_date=effective_date,
        temporal_state=temporal_state,
        ensure_retriever_fn=ensure_retriever_fn,
    )
    return RetrievalExecution(
        docs=docs,
        warnings=warnings,
        temporal_state=temporal_state,
        t_retrieve_ms=_elapsed_ms(retrieve_start),
    )


def resolve_retriever_state(
    *,
    retriever: object | None,
    warnings: Sequence[Mapping[str, object]] | None = None,
    retrieval_failure: Exception | None = None,
) -> RetrieverState:
    rag_enabled = bool(getattr(retriever, "enabled", True)) if retriever is not None else True
    retriever_ready = bool(getattr(retriever, "ready", True)) if retriever is not None else True
    failure_type = _maybe_text(getattr(retriever, "failure_type", None))
    disabled_reason = _maybe_text(getattr(retriever, "disabled_reason", None))
    index_path = _maybe_text(getattr(retriever, "index_path", None))
    model_name = _maybe_text(getattr(retriever, "model_name", None))

    if warnings:
        last_warning = warnings[-1]
        warning_code = _maybe_text(last_warning.get("code"))
        if warning_code == "retriever_disabled":
            rag_enabled = False
        if warning_code in {
            "retriever_error",
            "retriever_unavailable",
            "index_missing",
            "index_build_required",
            "retriever_not_ready",
        }:
            retriever_ready = False
        if warning_code and not failure_type:
            failure_type = warning_code

    if retrieval_failure is not None and not failure_type:
        failure_type = _maybe_text(getattr(retrieval_failure, "code", None)) or "retriever_error"

    return RetrieverState(
        rag_enabled=rag_enabled,
        retriever_ready=retriever_ready,
        failure_type=failure_type,
        disabled_reason=disabled_reason,
        index_path=index_path,
        model_name=model_name,
    )


def resolve_retrieval_empty_state(
    *,
    docs: Sequence[Mapping[str, object]],
    temporal_state: Mapping[str, object] | None,
    retriever_state: RetrieverState,
    retrieval_failure: Exception | None = None,
    warnings: Sequence[Mapping[str, object]] | None = None,
    prefer_warning_reason: bool = False,
) -> tuple[bool, str | None]:
    if not retriever_state.rag_enabled:
        return True, retriever_state.failure_type or "retriever_disabled"
    if retrieval_failure is not None:
        return True, retriever_state.failure_type or "retriever_error"
    if docs:
        return False, None

    temporal_state = temporal_state or {}
    temporal_reason = _maybe_text(temporal_state.get("refusal_reason"))
    if temporal_reason:
        return True, temporal_reason

    if prefer_warning_reason and warnings:
        warning_code = _maybe_text(warnings[-1].get("code"))
        if warning_code:
            return True, warning_code
    return True, "no_hits"


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


def execute_generation_sync(
    *,
    request: RagRequest,
    docs: Sequence[Mapping[str, object]],
    contexts: Sequence[str],
    temporal_state: Mapping[str, object] | None,
    raise_on_llm_error: bool = True,
    generate_chat_fn: Callable[..., str] = generate_chat,
    get_llm_config_fn: Callable[..., object] = get_llm_config,
) -> llm_runtime.GenerationResult:
    if not request.generate:
        return llm_runtime.build_generation_disabled_result(
            question=request.question,
            task=request.task,
            disabled_reason="generation_disabled_by_request",
            trace_id=request.trace_id,
        )

    prompt_start = time.perf_counter()
    prompt_artifacts = llm_runtime.build_prompt_artifacts(
        request.question,
        list(contexts),
        task=request.task,
        label_schema=request.label_schema,
        effective_date=_maybe_text((temporal_state or {}).get("effective_date")),
    )
    t_prompt_ms = _elapsed_ms(prompt_start)

    policy_decision = policy.evaluate_generation_policy(
        docs=docs,
        contexts=prompt_artifacts.redacted_contexts,
        temporal_state=temporal_state,
        refuse_on_empty=request.refuse_on_empty,
    )
    if policy_decision.should_refuse:
        generation = llm_runtime.build_refusal_result(
            policy_decision.refusal_payload or {},
            prompt_artifacts=prompt_artifacts,
            disabled_reason=policy_decision.disabled_reason or "insufficient_evidence",
            trace_id=request.trace_id,
        )
        generation.t_prompt_ms = t_prompt_ms
        return generation

    try:
        generation = llm_runtime.execute_sync_generation(
            prompt_artifacts,
            provider_override=request.provider,
            model_override=request.model,
            strict_output=request.strict_output,
            trace_id=request.trace_id,
            generate_chat_fn=generate_chat_fn,
            get_llm_config_fn=get_llm_config_fn,
            empty_collections_on_error=request.empty_collections_on_error,
        )
        generation.t_prompt_ms = t_prompt_ms
        return generation
    except llm_runtime.LLMExecutionError as exc:
        if raise_on_llm_error:
            raise
        return _provider_error_generation(
            code=exc.error_code,
            message=exc.disabled_reason,
            egress_decision=exc.egress_decision,
            provider_label=exc.provider_label,
            model_label=exc.model_label,
            llm_attempted=False,
            t_prompt_ms=t_prompt_ms,
        )


async def execute_generation_async(
    *,
    request: RagRequest,
    docs: Sequence[Mapping[str, object]],
    contexts: Sequence[str],
    temporal_state: Mapping[str, object] | None,
    run_generate: GenerateRunner,
) -> llm_runtime.GenerationResult:
    if not request.generate:
        return llm_runtime.build_generation_disabled_result(
            question=request.question,
            task=request.task,
            disabled_reason="generation_disabled_by_request",
            trace_id=request.trace_id,
        )

    prompt_start = time.perf_counter()
    prompt_artifacts = llm_runtime.build_prompt_artifacts(
        request.question,
        list(contexts),
        task=request.task,
        label_schema=request.label_schema,
        effective_date=_maybe_text((temporal_state or {}).get("effective_date")),
    )
    t_prompt_ms = _elapsed_ms(prompt_start)

    policy_decision = policy.evaluate_generation_policy(
        docs=docs,
        contexts=prompt_artifacts.redacted_contexts,
        temporal_state=temporal_state,
        refuse_on_empty=request.refuse_on_empty,
    )
    if policy_decision.should_refuse:
        generation = llm_runtime.build_refusal_result(
            policy_decision.refusal_payload or {},
            prompt_artifacts=prompt_artifacts,
            disabled_reason=policy_decision.disabled_reason or "insufficient_evidence",
            trace_id=request.trace_id,
        )
        generation.t_prompt_ms = t_prompt_ms
        return generation

    try:
        llm_request = llm_runtime.resolve_llm_request(
            prompt_artifacts,
            provider_override=request.provider,
            model_override=request.model,
            trace_id=request.trace_id,
        )
    except llm_runtime.LLMExecutionError as exc:
        return _provider_error_generation(
            code=exc.error_code,
            message=exc.disabled_reason,
            egress_decision=exc.egress_decision,
            provider_label=exc.provider_label,
            model_label=exc.model_label,
            llm_attempted=False,
            t_prompt_ms=t_prompt_ms,
        )

    llm_start = time.perf_counter()
    try:
        if llm_request.execution_mode == "local":
            raw_answer = await asyncio.to_thread(
                llm_runtime.generate_local_chat,
                prompt_artifacts.prompt,
                provider_cfg=llm_request.provider_config,
            )
        else:
            raw_answer = await run_generate(
                prompt_artifacts.prompt,
                llm_request.provider_label,
                llm_request.model_label,
            )
    except LLMProviderError as exc:
        return _provider_error_generation(
            code="llm_unavailable",
            message=str(exc),
            egress_decision=llm_request.build_egress_decision(
                remote_enabled=llm_request.execution_mode == "remote",
                disabled_reason=str(exc),
                trace_id=request.trace_id,
            ),
            provider_label=llm_request.provider_label,
            model_label=llm_request.model_label,
            llm_attempted=True,
            t_prompt_ms=t_prompt_ms,
            t_llm_ms=_elapsed_ms(llm_start),
        )

    generation = llm_runtime.validate_generated_answer(
        str(raw_answer),
        prompt_artifacts=prompt_artifacts,
        provider_label=llm_request.provider_label,
        model_label=llm_request.model_label,
        egress_decision=llm_request.build_egress_decision(
            remote_enabled=llm_request.execution_mode == "remote",
            disabled_reason=None,
            trace_id=request.trace_id,
        ),
        strict_output=request.strict_output,
        empty_collections_on_error=request.empty_collections_on_error,
    )
    generation.t_prompt_ms = t_prompt_ms
    generation.t_llm_ms = _elapsed_ms(llm_start)
    return generation


def generation_status_code(generation: llm_runtime.GenerationResult) -> int:
    if generation.output_ok:
        return 200
    code = _maybe_text((generation.output_error or {}).get("code"))
    if code in {"llm_unavailable", "llm_disabled"} and not generation.llm_enabled:
        return 503
    return 422


__all__ = [
    "GenerateRunner",
    "RagRequest",
    "RetrievalExecution",
    "RetrieverState",
    "execute_generation_async",
    "execute_generation_sync",
    "generation_status_code",
    "resolve_retrieval_empty_state",
    "resolve_retriever_state",
    "run_retrieval_sync",
]
