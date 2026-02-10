from __future__ import annotations

"""Data egress decision records and deterministic hashing utilities."""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from earCrawler.privacy.redaction import scrub_text

POLICY_VERSION = "data-egress.v1"
_REDACTION_MODES = {"none", "env_rules_v1"}


@dataclass
class DataEgressDecision:
    remote_enabled: bool
    disabled_reason: str | None
    provider: str | None
    model: str | None
    redaction_mode: str
    question_hash: str | None = None
    context_hashes: list[str] = field(default_factory=list)
    prompt_hash: str | None = None
    context_count: int = 0
    trace_id: str | None = None
    policy_version: str = POLICY_VERSION
    corpus_ref: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(value: str) -> str:
    normalized = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).rstrip("\n")


def hash_text(s: str) -> str:
    return hashlib.sha256(normalize_text(s).encode("utf-8")).hexdigest()


def _normalize_for_hash(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _normalize_for_hash(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_for_hash(v) for v in value]
    if isinstance(value, str):
        return normalize_text(value)
    return value


def hash_messages(messages: list[dict]) -> str:
    normalized = _normalize_for_hash(messages)
    payload = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize_context_hashes(contexts: Sequence[str]) -> list[str]:
    return [hash_text(str(context or "")) for context in contexts]


def resolve_redaction_mode(mode: str | None = None) -> str:
    resolved = (mode or os.getenv("EARCRAWLER_LLM_REDACTION_MODE", "none")).strip().lower()
    if resolved not in _REDACTION_MODES:
        return "none"
    return resolved


def redact_text_for_mode(text: str, *, mode: str) -> str:
    if mode == "env_rules_v1":
        return scrub_text(text or "")
    return text or ""


def redact_contexts(contexts: Sequence[str], *, mode: str) -> list[str]:
    return [redact_text_for_mode(str(ctx or ""), mode=mode) for ctx in contexts]


def redact_messages(messages: list[dict[str, Any]], *, mode: str) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for message in messages:
        cloned: dict[str, Any] = dict(message)
        content = cloned.get("content")
        if isinstance(content, str):
            cloned["content"] = redact_text_for_mode(content, mode=mode)
        redacted.append(cloned)
    return redacted


def build_data_egress_decision(
    *,
    remote_enabled: bool,
    disabled_reason: str | None,
    provider: str | None,
    model: str | None,
    redaction_mode: str,
    question: str | None,
    contexts: Sequence[str],
    messages: list[dict[str, Any]] | None,
    trace_id: str | None = None,
    corpus_ref: str | None = None,
) -> DataEgressDecision:
    question_hash = hash_text(question or "") if question is not None else None
    prompt_hash = hash_messages(messages) if messages is not None else None
    return DataEgressDecision(
        remote_enabled=bool(remote_enabled),
        disabled_reason=disabled_reason,
        provider=provider,
        model=model,
        redaction_mode=redaction_mode,
        question_hash=question_hash,
        context_hashes=summarize_context_hashes(contexts),
        prompt_hash=prompt_hash,
        context_count=len(list(contexts)),
        trace_id=trace_id,
        corpus_ref=corpus_ref,
    )


__all__ = [
    "DataEgressDecision",
    "POLICY_VERSION",
    "build_data_egress_decision",
    "hash_messages",
    "hash_text",
    "redact_contexts",
    "redact_messages",
    "redact_text_for_mode",
    "resolve_redaction_mode",
    "summarize_context_hashes",
]
