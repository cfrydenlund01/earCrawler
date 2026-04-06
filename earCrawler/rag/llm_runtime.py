from __future__ import annotations

"""Prompt planning, provider invocation, and schema validation helpers."""

import json
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from api_clients.llm_client import LLMProviderError, generate_chat
from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.rag.local_adapter_runtime import generate_local_chat
from earCrawler.rag.output_schema import (
    DEFAULT_ALLOWED_LABELS,
    TRUTHINESS_LABELS,
    OutputSchemaError,
    make_unanswerable_payload,
    validate_and_extract_strict_answer,
)
from earCrawler.security.data_egress import (
    DataEgressDecision,
    build_data_egress_decision,
    redact_contexts,
    redact_text_for_mode,
    resolve_redaction_mode,
)


@dataclass(frozen=True)
class PromptArtifacts:
    prompt_question: str
    redaction_mode: str
    redacted_question: str
    redacted_contexts: list[str]
    prompt: list[dict[str, str]]
    allowed_labels: set[str]


@dataclass(frozen=True)
class ResolvedLLMRequest:
    provider_label: str
    model_label: str
    prompt_artifacts: PromptArtifacts
    execution_mode: str = "remote"
    provider_config: object | None = None

    def build_egress_decision(
        self,
        *,
        remote_enabled: bool,
        disabled_reason: str | None,
        trace_id: str | None,
    ) -> DataEgressDecision:
        return build_data_egress_decision(
            remote_enabled=remote_enabled,
            disabled_reason=disabled_reason,
            provider=self.provider_label,
            model=self.model_label,
            redaction_mode=self.prompt_artifacts.redaction_mode,
            question=self.prompt_artifacts.redacted_question,
            contexts=self.prompt_artifacts.redacted_contexts,
            messages=self.prompt_artifacts.prompt,
            trace_id=trace_id,
        )


@dataclass
class GenerationResult:
    answer_text: str | None = None
    label: str | None = None
    justification: str | None = None
    citations: list[dict] | None = None
    evidence_okay: dict | None = None
    assumptions: list[str] | None = None
    citation_span_ids: list[str] | None = None
    provider_label: str | None = None
    model_label: str | None = None
    llm_enabled: bool = False
    llm_attempted: bool = False
    raw_answer: str | None = None
    disabled_reason: str | None = None
    output_ok: bool = True
    output_error: dict | None = None
    egress_decision: DataEgressDecision | None = None
    prompt: list[dict[str, str]] | None = None
    t_prompt_ms: float = 0.0
    t_llm_ms: float = 0.0
    t_parse_ms: float = 0.0


class LLMExecutionError(LLMProviderError):
    def __init__(
        self,
        message: str,
        *,
        egress_decision: DataEgressDecision,
        error_code: str,
        provider_label: str | None = None,
        model_label: str | None = None,
        disabled_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.egress_decision = egress_decision
        self.error_code = error_code
        self.provider_label = provider_label
        self.model_label = model_label
        self.disabled_reason = disabled_reason or message


def build_prompt_messages(
    question: str,
    contexts: Sequence[str],
    *,
    label_schema: str | None = None,
    effective_date: str | None = None,
) -> list[dict[str, str]]:
    temporal_instruction = ""
    if effective_date:
        temporal_instruction = (
            f"Temporal scope: answer only from evidence applicable on {effective_date}. "
            "If the dated evidence does not support a grounded answer, respond with label=unanswerable.\n\n"
        )
    if label_schema == "truthiness":
        allowed_labels = "true, false, unanswerable"
        system = (
            "You are an expert on Export Administration Regulations (EAR). "
            "Answer ONLY using the provided regulation excerpts and knowledge-graph context. "
            "Cite EAR section IDs when possible. If the answer is not determinable from the "
            "provided text, say so explicitly.\n\n"
            f"{temporal_instruction}"
            "Truthiness labeling (MUST match exactly):\n"
            f"- Allowed labels: {allowed_labels}\n"
            "- Definitions:\n"
            "  - true: the statement in the question is supported by the provided context.\n"
            "  - false: the statement is not supported or is contradicted by the provided context.\n"
            "  - unanswerable: the provided context is insufficient to decide true vs false.\n\n"
            "Respond in STRICT JSON with this exact shape and no extra text:\n"
            "{\n"
            '  "label": "<one of: '
            + allowed_labels
            + '>\",\n'
            '  "answer_text": "<short answer>",\n'
            "  \"citations\": [\n"
            '    {"section_id": "EAR-<id>", "quote": "<verbatim substring from Context>", "span_id": "<optional>"}\n'
            "  ],\n"
            '  "evidence_okay": {"ok": true, "reasons": ["<brief machine-checkable reasons>"]},\n'
            '  "assumptions": []\n'
            "}\n\n"
            "Grounding rules (MUST follow):\n"
            "- Every citation.quote MUST be an exact substring of the provided Context (verbatim).\n"
            "- If you cannot provide at least one grounded quote for the key claim, set label=unanswerable.\n"
            "- If label=unanswerable, answer_text MUST include a short refusal and a retrieval-guidance hint (e.g., missing ECCN/destination/end-use).\n"
            "- evidence_okay.ok MUST be true when you followed these rules.\n"
        )
        context_block = "\n\n".join(contexts) if contexts else "No supporting context provided."
        user = f"Context:\n{context_block}\n\nQuestion: {question}\nAnswer JSON:"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    allowed_labels = (
        "license_required, no_license_required, exception_applies, "
        "permitted_with_license, permitted, prohibited, unanswerable"
    )
    system = (
        "You are an expert on Export Administration Regulations (EAR). "
        "Answer ONLY using the provided regulation excerpts and knowledge-graph context. "
        "Cite EAR section IDs when possible. If the answer is not determinable from the "
        "provided text, say so explicitly.\n\n"
        f"{temporal_instruction}"
        "Label taxonomy (MUST match exactly):\n"
        f"- Allowed labels: {allowed_labels}\n"
        "- Definitions:\n"
        "  - license_required: the question asks whether a license is required and the context supports that it is.\n"
        "  - no_license_required: the question asks whether a license is required and the context supports that it is not.\n"
        "  - exception_applies: a License Exception applies so export can proceed without a license.\n"
        "  - permitted_with_license: export/activity is allowed, but ONLY if a license is obtained.\n"
        "  - permitted: export/activity is allowed as described (no additional requirement stated in provided context).\n"
        "  - prohibited: export/activity is not allowed as described.\n"
        "  - unanswerable: the provided context does not support any of the above.\n\n"
        "Task-aware label rules:\n"
        "- If the question is phrased as 'need a license / license required?', choose among: "
        "license_required | no_license_required | exception_applies | unanswerable.\n"
        "- If the question is phrased as 'can X export ... without a license?', then:\n"
        "  - If context implies a license must be obtained: permitted_with_license.\n"
        "  - If a License Exception applies: exception_applies.\n"
        "  - If context implies it is allowed without a license: no_license_required.\n"
        "- Dataset convention: when task=entity_obligation and a License Exception applies, "
        "use label=permitted (NOT exception_applies).\n"
        "- Avoid using prohibited unless the provided excerpts explicitly prohibit the export/activity.\n\n"
        "Decision table (use verbatim logic):\n"
        "- If answer is 'No' to 'without a license?' because a license is required => permitted_with_license.\n"
        "- If a License Exception applies => exception_applies.\n"
        "- If you cannot cite a relevant EAR section from the provided context => unanswerable.\n\n"
        "Examples:\n"
        "Example A (exception applies):\n"
        "Context: [EAR-740.1] License Exceptions describe conditions where exports may be made without a license.\n"
        "Question: Can a controlled item be exported without a license if a License Exception applies under the EAR?\n"
        "Answer JSON:\n"
        "{\n"
        '  "label": "exception_applies",\n'
        '  "answer_text": "Yes. Insufficient evidence to apply conditions unless the cited exception applies; if it does, the export can proceed without a license.",\n'
        "  \"citations\": [\n"
        '    {"section_id": "EAR-740.1", "quote": "License Exceptions describe conditions where exports may be made without a license.", "span_id": ""}\n'
        "  ],\n"
        '  "evidence_okay": {"ok": true, "reasons": ["citation_quote_is_substring_of_context"]},\n'
        '  "assumptions": []\n'
        "}\n"
        "Example B (permitted with license):\n"
        "Context: [EAR-742.4(a)(1)] A license is required to export certain high-performance computers to China.\n"
        "Question: Can ACME export a high-performance computer to China without a license?\n"
        "Answer JSON:\n"
        "{\n"
        '  "label": "permitted_with_license",\n'
        '  "answer_text": "No. The activity is only permitted with a license based on the provided excerpt.",\n'
        "  \"citations\": [\n"
        '    {"section_id": "EAR-742.4(a)(1)", "quote": "A license is required to export certain high-performance computers to China.", "span_id": ""}\n'
        "  ],\n"
        '  "evidence_okay": {"ok": true, "reasons": ["citation_quote_is_substring_of_context"]},\n'
        '  "assumptions": []\n'
        "}\n\n"
        "Respond in STRICT JSON with this exact shape and no extra text:\n"
        "{\n"
        '  "label": "<one of: '
        + allowed_labels
        + '>\",\n'
        '  "answer_text": "<short answer>",\n'
        '  "justification": "<1-2 sentences summarizing evidence>",\n'
        "  \"citations\": [\n"
        '    {"section_id": "EAR-<id>", "quote": "<verbatim substring from Context>", "span_id": "<optional>"}\n'
        "  ],\n"
        '  "evidence_okay": {"ok": true, "reasons": ["<brief machine-checkable reasons>"]},\n'
        '  "assumptions": []\n'
        "}\n\n"
        "Grounding rules (MUST follow):\n"
        "- Every citation.quote MUST be an exact substring of the provided Context (verbatim).\n"
        "- If you cannot provide at least one grounded quote for the key claim, set label=unanswerable.\n"
        "- If label=unanswerable, answer_text MUST include a short refusal and a retrieval-guidance hint (e.g., missing ECCN/destination/end-use).\n"
        "- If assumptions is non-empty, label MUST be unanswerable unless each assumption is directly supported by the Context.\n"
        "- evidence_okay.ok MUST be true when you followed these rules.\n"
    )
    context_block = "\n\n".join(contexts) if contexts else "No supporting context provided."
    user = f"Context:\n{context_block}\n\nQuestion: {question}\nAnswer JSON:"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_prompt_artifacts(
    question: str,
    contexts: Sequence[str],
    *,
    task: str | None = None,
    label_schema: str | None = None,
    effective_date: str | None = None,
) -> PromptArtifacts:
    prompt_question = question if not task else f"(task={task}) {question}"
    redaction_mode = resolve_redaction_mode()
    redacted_question = redact_text_for_mode(prompt_question, mode=redaction_mode)
    redacted_contexts = redact_contexts(contexts, mode=redaction_mode)
    prompt = build_prompt_messages(
        redacted_question,
        redacted_contexts,
        label_schema=label_schema,
        effective_date=effective_date,
    )
    allowed_labels = (
        TRUTHINESS_LABELS if label_schema == "truthiness" else DEFAULT_ALLOWED_LABELS
    )
    return PromptArtifacts(
        prompt_question=prompt_question,
        redaction_mode=redaction_mode,
        redacted_question=redacted_question,
        redacted_contexts=redacted_contexts,
        prompt=prompt,
        allowed_labels=set(allowed_labels),
    )


def _empty_error_collections(
    enabled: bool,
) -> tuple[list[dict] | None, list[str] | None, list[str] | None]:
    if enabled:
        return [], [], []
    return None, None, None


def _recover_local_invalid_json_result(
    *,
    raw_text: str,
    prompt_artifacts: PromptArtifacts,
    provider_label: str | None,
    model_label: str | None,
    egress_decision: DataEgressDecision,
    parse_start: float,
) -> GenerationResult:
    fallback_payload = make_unanswerable_payload(
        hint="ECCN, destination, and end-use details from retrieved EAR context",
        justification=(
            "Local adapter returned invalid JSON; emitted strict unanswerable fallback."
        ),
        evidence_reasons=["model_invalid_json_fallback"],
    )
    validated = validate_and_extract_strict_answer(
        json.dumps(fallback_payload, ensure_ascii=True, separators=(",", ":")),
        allowed_labels=prompt_artifacts.allowed_labels,
        context="\n\n".join(prompt_artifacts.redacted_contexts),
        contexts=prompt_artifacts.redacted_contexts,
    )
    return GenerationResult(
        answer_text=str(validated["answer_text"]),
        label=str(validated["label"]),
        justification=validated.get("justification"),
        citations=list(validated.get("citations") or []),
        evidence_okay=dict(validated.get("evidence_okay") or {}),
        assumptions=list(validated.get("assumptions") or []),
        citation_span_ids=list(validated.get("citation_span_ids") or []),
        provider_label=provider_label,
        model_label=model_label,
        llm_enabled=True,
        llm_attempted=True,
        raw_answer=raw_text,
        disabled_reason=None,
        output_ok=True,
        output_error=None,
        egress_decision=egress_decision,
        prompt=prompt_artifacts.prompt,
        t_parse_ms=round((time.perf_counter() - parse_start) * 1000.0, 3),
    )


def validate_generated_answer(
    raw_answer: str,
    *,
    prompt_artifacts: PromptArtifacts,
    provider_label: str | None,
    model_label: str | None,
    egress_decision: DataEgressDecision,
    strict_output: bool,
    empty_collections_on_error: bool,
) -> GenerationResult:
    parse_start = time.perf_counter()
    raw_text = str(raw_answer)
    try:
        validated = validate_and_extract_strict_answer(
            raw_text,
            allowed_labels=prompt_artifacts.allowed_labels,
            context="\n\n".join(prompt_artifacts.redacted_contexts),
            contexts=prompt_artifacts.redacted_contexts,
        )
    except OutputSchemaError as exc:
        if (
            strict_output
            and provider_label == "local_adapter"
            and exc.code == "invalid_json"
        ):
            return _recover_local_invalid_json_result(
                raw_text=raw_text,
                prompt_artifacts=prompt_artifacts,
                provider_label=provider_label,
                model_label=model_label,
                egress_decision=egress_decision,
                parse_start=parse_start,
            )
        citations, assumptions, citation_span_ids = _empty_error_collections(
            empty_collections_on_error
        )
        answer_text = raw_text if not strict_output else None
        return GenerationResult(
            answer_text=answer_text,
            label=None,
            justification=None,
            citations=citations,
            evidence_okay=None,
            assumptions=assumptions,
            citation_span_ids=citation_span_ids,
            provider_label=provider_label,
            model_label=model_label,
            llm_enabled=True,
            llm_attempted=True,
            raw_answer=raw_text,
            disabled_reason=None,
            output_ok=False,
            output_error=exc.as_dict(),
            egress_decision=egress_decision,
            prompt=prompt_artifacts.prompt,
            t_parse_ms=round((time.perf_counter() - parse_start) * 1000.0, 3),
        )

    return GenerationResult(
        answer_text=str(validated["answer_text"]),
        label=str(validated["label"]),
        justification=validated.get("justification"),
        citations=list(validated.get("citations") or []),
        evidence_okay=dict(validated.get("evidence_okay") or {}),
        assumptions=list(validated.get("assumptions") or []),
        citation_span_ids=list(validated.get("citation_span_ids") or []),
        provider_label=provider_label,
        model_label=model_label,
        llm_enabled=True,
        llm_attempted=True,
        raw_answer=raw_text,
        disabled_reason=None,
        output_ok=True,
        output_error=None,
        egress_decision=egress_decision,
        prompt=prompt_artifacts.prompt,
        t_parse_ms=round((time.perf_counter() - parse_start) * 1000.0, 3),
    )


def resolve_llm_request(
    prompt_artifacts: PromptArtifacts,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    trace_id: str | None = None,
    get_llm_config_fn: Callable[..., object] = get_llm_config,
) -> ResolvedLLMRequest:
    try:
        config = get_llm_config_fn(
            provider_override=provider_override,
            model_override=model_override,
        )
    except ValueError as exc:
        egress_decision = build_data_egress_decision(
            remote_enabled=False,
            disabled_reason=str(exc),
            provider=None,
            model=None,
            redaction_mode=prompt_artifacts.redaction_mode,
            question=prompt_artifacts.redacted_question,
            contexts=prompt_artifacts.redacted_contexts,
            messages=prompt_artifacts.prompt,
            trace_id=trace_id,
        )
        raise LLMExecutionError(
            str(exc),
            egress_decision=egress_decision,
            error_code="llm_unavailable",
            disabled_reason=str(exc),
        ) from exc

    provider_label = config.provider.provider
    model_label = config.provider.model
    request = ResolvedLLMRequest(
        provider_label=provider_label,
        model_label=model_label,
        prompt_artifacts=prompt_artifacts,
        execution_mode=getattr(config, "execution_mode", "remote"),
        provider_config=getattr(config, "provider", None),
    )
    if request.execution_mode == "local":
        if getattr(config, "enable_local", False):
            return request
        disabled_reason = getattr(config, "local_disabled_reason", None) or (
            "local adapter runtime is disabled"
        )
        raise LLMExecutionError(
            (
                f"Local adapter generation is disabled ({disabled_reason}). "
                "Set LLM_PROVIDER=local_adapter and EARCRAWLER_ENABLE_LOCAL_LLM=1."
            ),
            egress_decision=request.build_egress_decision(
                remote_enabled=False,
                disabled_reason=disabled_reason,
                trace_id=trace_id,
            ),
            error_code="llm_disabled",
            provider_label=provider_label,
            model_label=model_label,
            disabled_reason=disabled_reason,
        )
    if not config.enable_remote:
        disabled_reason = config.remote_disabled_reason or "remote LLM policy denied egress"
        raise LLMExecutionError(
            (
                f"Remote LLM calls are disabled ({disabled_reason}). "
                "Remote use requires EARCRAWLER_REMOTE_LLM_POLICY=allow and "
                "EARCRAWLER_ENABLE_REMOTE_LLM=1."
            ),
            egress_decision=request.build_egress_decision(
                remote_enabled=False,
                disabled_reason=disabled_reason,
                trace_id=trace_id,
            ),
            error_code="llm_disabled",
            provider_label=provider_label,
            model_label=model_label,
            disabled_reason=disabled_reason,
        )
    return request


def build_refusal_result(
    refusal_payload: dict[str, object],
    *,
    prompt_artifacts: PromptArtifacts,
    disabled_reason: str,
    trace_id: str | None,
) -> GenerationResult:
    egress_decision = build_data_egress_decision(
        remote_enabled=False,
        disabled_reason=disabled_reason,
        provider=None,
        model=None,
        redaction_mode=prompt_artifacts.redaction_mode,
        question=prompt_artifacts.redacted_question,
        contexts=prompt_artifacts.redacted_contexts,
        messages=prompt_artifacts.prompt,
        trace_id=trace_id,
    )
    rendered = json.dumps(
        refusal_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    validated = validate_and_extract_strict_answer(
        rendered,
        allowed_labels=prompt_artifacts.allowed_labels,
        context="\n\n".join(prompt_artifacts.redacted_contexts),
        contexts=prompt_artifacts.redacted_contexts,
    )
    return GenerationResult(
        answer_text=str(validated["answer_text"]),
        label=str(validated["label"]),
        justification=validated.get("justification"),
        citations=list(validated.get("citations") or []),
        evidence_okay=dict(validated.get("evidence_okay") or {}),
        assumptions=list(validated.get("assumptions") or []),
        citation_span_ids=list(validated.get("citation_span_ids") or []),
        provider_label=None,
        model_label=None,
        llm_enabled=False,
        llm_attempted=False,
        raw_answer=None,
        disabled_reason=disabled_reason,
        output_ok=True,
        output_error=None,
        egress_decision=egress_decision,
        prompt=prompt_artifacts.prompt,
    )


def build_generation_disabled_result(
    *,
    question: str,
    task: str | None = None,
    disabled_reason: str,
    trace_id: str | None,
) -> GenerationResult:
    prompt_question = question if not task else f"(task={task}) {question}"
    redaction_mode = resolve_redaction_mode()
    redacted_question = redact_text_for_mode(prompt_question, mode=redaction_mode)
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
    return GenerationResult(
        provider_label=None,
        model_label=None,
        llm_enabled=False,
        llm_attempted=False,
        raw_answer=None,
        disabled_reason=disabled_reason,
        output_ok=True,
        output_error=None,
        egress_decision=egress_decision,
        prompt=None,
    )


def execute_sync_generation(
    prompt_artifacts: PromptArtifacts,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    strict_output: bool,
    trace_id: str | None,
    generate_chat_fn: Callable[..., str] = generate_chat,
    get_llm_config_fn: Callable[..., object] = get_llm_config,
    empty_collections_on_error: bool,
) -> GenerationResult:
    request = resolve_llm_request(
        prompt_artifacts,
        provider_override=provider_override,
        model_override=model_override,
        trace_id=trace_id,
        get_llm_config_fn=get_llm_config_fn,
    )
    llm_start = time.perf_counter()
    remote_enabled = request.execution_mode == "remote"
    try:
        if request.execution_mode == "local":
            raw_answer = generate_local_chat(
                prompt_artifacts.prompt,
                provider_cfg=request.provider_config,
                require_valid_json=bool(strict_output),
            )
        else:
            raw_answer = generate_chat_fn(
                prompt_artifacts.prompt,
                provider=request.provider_label,
                model=request.model_label,
            )
    except LLMProviderError as exc:
        raise LLMExecutionError(
            str(exc),
            egress_decision=request.build_egress_decision(
                remote_enabled=remote_enabled,
                disabled_reason=str(exc),
                trace_id=trace_id,
            ),
            error_code="llm_unavailable",
            provider_label=request.provider_label,
            model_label=request.model_label,
            disabled_reason=str(exc),
        ) from exc

    result = validate_generated_answer(
        str(raw_answer),
        prompt_artifacts=prompt_artifacts,
        provider_label=request.provider_label,
        model_label=request.model_label,
        egress_decision=request.build_egress_decision(
            remote_enabled=remote_enabled,
            disabled_reason=None,
            trace_id=trace_id,
        ),
        strict_output=strict_output,
        empty_collections_on_error=empty_collections_on_error,
    )
    result.t_llm_ms = round((time.perf_counter() - llm_start) * 1000.0, 3)
    return result


__all__ = [
    "GenerationResult",
    "LLMExecutionError",
    "PromptArtifacts",
    "ResolvedLLMRequest",
    "build_generation_disabled_result",
    "build_prompt_artifacts",
    "build_prompt_messages",
    "build_refusal_result",
    "execute_sync_generation",
    "resolve_llm_request",
    "validate_generated_answer",
]
