from __future__ import annotations

"""Temporal and thin-evidence policy helpers for RAG answer generation."""

import os
from dataclasses import dataclass
from typing import Mapping, Sequence

from earCrawler.rag.output_schema import make_unanswerable_payload

DEFAULT_THIN_RETRIEVAL_HINT = (
    "the relevant EAR excerpt(s) for this scenario "
    "(for example: ECCN, destination, end user/end use)"
)


def env_truthy(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, *, default: int, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return max(min_value, value)


def env_float(name: str, *, default: float, min_value: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    return max(min_value, value)


def max_retrieval_score(docs: Sequence[Mapping[str, object]]) -> float:
    best = 0.0
    for doc in docs or []:
        score = doc.get("score")
        if isinstance(score, (int, float)):
            best = max(best, float(score))
        elif isinstance(score, str):
            try:
                best = max(best, float(score))
            except ValueError:
                continue
    return best


def total_context_chars(contexts: Sequence[str]) -> int:
    return sum(len(str(context or "")) for context in (contexts or []))


def temporal_refusal_payload(decision: Mapping[str, object]) -> dict[str, object]:
    reason = str(decision.get("refusal_reason") or "").strip()
    effective_date = str(decision.get("effective_date") or "").strip()
    if reason == "conflicting_effective_dates":
        return make_unanswerable_payload(
            hint="one effective date for the question (the request parameter and question text disagree)",
            justification="The request supplied conflicting temporal anchors, so the answer cannot be grounded to one regulatory date.",
            evidence_reasons=["conflicting_effective_dates"],
        )
    if reason == "multiple_dates_in_question":
        return make_unanswerable_payload(
            hint="one effective date for the question instead of multiple dates",
            justification="The question contains multiple effective dates and the runtime refuses to guess which date governs applicability.",
            evidence_reasons=["multiple_dates_in_question"],
        )
    if reason == "temporal_evidence_ambiguous":
        hint = "regulatory text with explicit effective dates"
        if effective_date:
            hint = f"regulatory text with explicit effective dates applicable on {effective_date}"
        return make_unanswerable_payload(
            hint=hint,
            justification="Retrieved evidence does not establish which version is applicable on the requested date.",
            evidence_reasons=["temporal_evidence_ambiguous"],
        )
    hint = "regulatory text applicable on the requested effective date"
    if effective_date:
        hint = f"regulatory text applicable on {effective_date}"
    return make_unanswerable_payload(
        hint=hint,
        justification="No retrieved evidence was applicable on the requested effective date.",
        evidence_reasons=["no_temporally_applicable_evidence"],
    )


@dataclass(frozen=True)
class GenerationPolicyDecision:
    should_refuse: bool
    disabled_reason: str | None = None
    refusal_payload: dict[str, object] | None = None


def evaluate_generation_policy(
    *,
    docs: Sequence[Mapping[str, object]],
    contexts: Sequence[str],
    temporal_state: Mapping[str, object] | None,
    refuse_on_empty: bool,
    thin_retrieval_hint: str = DEFAULT_THIN_RETRIEVAL_HINT,
) -> GenerationPolicyDecision:
    temporal_state = temporal_state or {}
    temporal_should_refuse = bool(temporal_state.get("should_refuse"))
    temporal_refusal_reason = str(temporal_state.get("refusal_reason") or "").strip() or None

    refuse_on_thin = env_truthy("EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL", default=False)
    min_docs = env_int("EARCRAWLER_THIN_RETRIEVAL_MIN_DOCS", default=1, min_value=1)
    min_top_score = env_float(
        "EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE",
        default=0.0,
        min_value=0.0,
    )
    min_total_chars = env_int(
        "EARCRAWLER_THIN_RETRIEVAL_MIN_TOTAL_CHARS",
        default=0,
        min_value=0,
    )

    thin_retrieval = temporal_should_refuse or (refuse_on_empty and len(docs) == 0)
    if not thin_retrieval and refuse_on_thin:
        thin_retrieval = len(docs) == 0
        if not thin_retrieval:
            if len(docs) < min_docs:
                thin_retrieval = True
            elif max_retrieval_score(docs) < min_top_score:
                thin_retrieval = True
            elif total_context_chars(contexts) < min_total_chars:
                thin_retrieval = True

    if not thin_retrieval:
        return GenerationPolicyDecision(should_refuse=False)

    if temporal_should_refuse:
        return GenerationPolicyDecision(
            should_refuse=True,
            disabled_reason=temporal_refusal_reason or "temporal_evidence_ambiguous",
            refusal_payload=temporal_refusal_payload(temporal_state),
        )

    return GenerationPolicyDecision(
        should_refuse=True,
        disabled_reason="insufficient_evidence",
        refusal_payload=make_unanswerable_payload(
            hint=thin_retrieval_hint,
            justification="Retrieval evidence was empty or too thin to ground a compliant answer.",
            evidence_reasons=["thin_or_empty_retrieval"],
        ),
    )


__all__ = [
    "DEFAULT_THIN_RETRIEVAL_HINT",
    "GenerationPolicyDecision",
    "env_float",
    "env_int",
    "env_truthy",
    "evaluate_generation_policy",
    "max_retrieval_score",
    "temporal_refusal_payload",
    "total_context_chars",
]
