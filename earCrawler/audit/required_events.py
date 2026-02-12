from __future__ import annotations

"""Minimum audit event helpers for eval + HITL workflows."""

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from earCrawler.audit import ledger

QUERY_OUTCOME_EVENTS = frozenset({"query_answered", "query_refused"})
QUERY_OUTCOME_REQUIREMENT = "query_outcome"

REQUIRED_EVENTS_BY_SCOPE: dict[str, tuple[str, ...]] = {
    "ci_eval": (
        "run_started",
        "snapshot_selected",
        "index_selected",
        "remote_llm_policy_decision",
        QUERY_OUTCOME_REQUIREMENT,
    ),
    "local_dev": (
        "run_started",
        "remote_llm_policy_decision",
        QUERY_OUTCOME_REQUIREMENT,
    ),
    "operator_production": (
        "run_started",
        "snapshot_selected",
        "index_selected",
        "remote_llm_policy_decision",
        QUERY_OUTCOME_REQUIREMENT,
    ),
}


def required_events_for_scope(scope: str) -> tuple[str, ...]:
    normalized = str(scope or "ci_eval").strip().lower()
    return REQUIRED_EVENTS_BY_SCOPE.get(normalized, REQUIRED_EVENTS_BY_SCOPE["ci_eval"])


def _normalized_payload(payload: Mapping[str, object] | None) -> dict[str, object]:
    return dict(payload or {})


def _coerce_run_id(run_id: str | None) -> str:
    value = str(run_id or "").strip()
    return value or "adhoc"


def emit_run_started(
    *,
    run_id: str,
    run_kind: str,
    dataset_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> None:
    payload = {
        "run_id": _coerce_run_id(run_id),
        "run_kind": str(run_kind or "unknown"),
        "dataset_id": str(dataset_id or "") or None,
        "metadata": _normalized_payload(metadata),
    }
    ledger.append_fact("run_started", payload, run_id=run_id)


def emit_snapshot_selected(
    *,
    run_id: str,
    snapshot_id: str | None,
    snapshot_sha256: str | None,
    corpus_digest: str | None = None,
) -> None:
    payload = {
        "run_id": _coerce_run_id(run_id),
        "snapshot_id": str(snapshot_id or "unknown").strip() or "unknown",
        "snapshot_sha256": str(snapshot_sha256 or "unknown").strip() or "unknown",
        "corpus_digest": str(corpus_digest or "unknown").strip() or "unknown",
    }
    ledger.append_fact("snapshot_selected", payload, run_id=run_id)


def emit_index_selected(
    *,
    run_id: str,
    index_path: str,
    index_sha256: str | None,
    index_meta_path: str | None,
    index_meta_sha256: str | None,
    embedding_model: str | None,
) -> None:
    payload = {
        "run_id": _coerce_run_id(run_id),
        "index_path": str(index_path or "").strip(),
        "index_sha256": str(index_sha256 or "unknown").strip() or "unknown",
        "index_meta_path": str(index_meta_path or "").strip() or None,
        "index_meta_sha256": str(index_meta_sha256 or "").strip() or None,
        "embedding_model": str(embedding_model or "unknown").strip() or "unknown",
    }
    ledger.append_fact("index_selected", payload, run_id=run_id)


def emit_remote_llm_policy_decision(
    *,
    trace_id: str | None,
    run_id: str | None,
    egress_decision: Mapping[str, object] | None,
) -> None:
    decision = _normalized_payload(egress_decision)
    remote_enabled = bool(decision.get("remote_enabled"))
    payload = {
        "run_id": str(run_id or "").strip() or None,
        "trace_id": str(trace_id or "").strip() or None,
        "outcome": "allow" if remote_enabled else "deny",
        "remote_enabled": remote_enabled,
        "remote_policy": str(
            os.getenv("EARCRAWLER_REMOTE_LLM_POLICY", "deny")
        ).strip().lower(),
        "remote_enable_flag": os.getenv("EARCRAWLER_ENABLE_REMOTE_LLM", "0") == "1",
        "provider": decision.get("provider"),
        "model": decision.get("model"),
        "disabled_reason": decision.get("disabled_reason"),
        "redaction_mode": decision.get("redaction_mode"),
        "policy_version": decision.get("policy_version"),
        "question_hash": decision.get("question_hash"),
        "prompt_hash": decision.get("prompt_hash"),
        "context_count": decision.get("context_count"),
    }
    ledger.append_fact(
        "remote_llm_policy_decision",
        payload,
        run_id=run_id,
    )


def emit_query_outcome(
    *,
    trace_id: str | None,
    run_id: str | None,
    label: str | None,
    answer_text: str | None,
    output_ok: bool,
    retrieval_empty: bool,
    retrieval_empty_reason: str | None,
    disabled_reason: str | None,
    output_error_code: str | None = None,
) -> str:
    normalized_label = str(label or "").strip().lower()
    has_answer = bool(str(answer_text or "").strip())
    refused = (not output_ok) or normalized_label == "unanswerable" or (not has_answer)
    event = "query_refused" if refused else "query_answered"
    payload = {
        "run_id": str(run_id or "").strip() or None,
        "trace_id": str(trace_id or "").strip() or None,
        "label": normalized_label or None,
        "output_ok": bool(output_ok),
        "retrieval_empty": bool(retrieval_empty),
        "retrieval_empty_reason": str(retrieval_empty_reason or "").strip() or None,
        "disabled_reason": str(disabled_reason or "").strip() or None,
        "output_error_code": str(output_error_code or "").strip() or None,
    }
    ledger.append_fact(event, payload, run_id=run_id)
    return event


def read_ledger_entries(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    if not path.exists():
        return entries
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                entries.append(payload)
    return entries


def _event_payload(entry: Mapping[str, object]) -> Mapping[str, object]:
    payload = entry.get("payload")
    if isinstance(payload, Mapping):
        return payload
    return {}


def filter_entries(
    entries: Sequence[Mapping[str, object]],
    *,
    run_id: str | None = None,
    trace_id: str | None = None,
) -> list[Mapping[str, object]]:
    filtered: list[Mapping[str, object]] = []
    run_filter = str(run_id or "").strip()
    trace_filter = str(trace_id or "").strip()
    for entry in entries:
        payload = _event_payload(entry)
        if run_filter:
            payload_run_id = str(payload.get("run_id") or "").strip()
            if payload_run_id != run_filter:
                continue
        if trace_filter:
            payload_trace_id = str(payload.get("trace_id") or "").strip()
            if payload_trace_id != trace_filter:
                continue
        filtered.append(entry)
    return filtered


def missing_required_events(
    entries: Sequence[Mapping[str, object]],
    *,
    required: Sequence[str],
) -> list[str]:
    observed = {str(entry.get("event") or "").strip() for entry in entries}
    missing: list[str] = []
    for requirement in required:
        if requirement == QUERY_OUTCOME_REQUIREMENT:
            if not (QUERY_OUTCOME_EVENTS & observed):
                missing.append(requirement)
            continue
        if requirement not in observed:
            missing.append(requirement)
    return missing


def verify_required_events(
    path: Path,
    *,
    scope: str = "ci_eval",
    run_id: str | None = None,
    trace_id: str | None = None,
    required: Sequence[str] | None = None,
) -> dict[str, object]:
    entries = read_ledger_entries(path)
    filtered = filter_entries(entries, run_id=run_id, trace_id=trace_id)
    required_events = tuple(required or required_events_for_scope(scope))
    missing = missing_required_events(filtered, required=required_events)
    observed = sorted({str(entry.get("event") or "").strip() for entry in filtered if entry.get("event")})
    return {
        "ok": len(missing) == 0,
        "path": str(path),
        "scope": str(scope or "ci_eval"),
        "run_id": str(run_id or "").strip() or None,
        "trace_id": str(trace_id or "").strip() or None,
        "required": list(required_events),
        "observed": observed,
        "missing": missing,
        "event_count": len(filtered),
    }


def assert_required_events(
    path: Path,
    *,
    scope: str = "ci_eval",
    run_id: str | None = None,
    trace_id: str | None = None,
    required: Sequence[str] | None = None,
) -> dict[str, object]:
    report = verify_required_events(
        path,
        scope=scope,
        run_id=run_id,
        trace_id=trace_id,
        required=required,
    )
    if not bool(report.get("ok")):
        missing = ", ".join(report.get("missing") or [])
        raise ValueError(f"Missing required audit events ({scope}): {missing}")
    return report


__all__ = [
    "QUERY_OUTCOME_EVENTS",
    "QUERY_OUTCOME_REQUIREMENT",
    "REQUIRED_EVENTS_BY_SCOPE",
    "assert_required_events",
    "emit_index_selected",
    "emit_query_outcome",
    "emit_remote_llm_policy_decision",
    "emit_run_started",
    "emit_snapshot_selected",
    "filter_entries",
    "missing_required_events",
    "read_ledger_entries",
    "required_events_for_scope",
    "verify_required_events",
]

