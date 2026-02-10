from __future__ import annotations

"""HITL decision-event schema and ledger ingestion helpers."""

from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from earCrawler.audit import ledger
from earCrawler.security.data_egress import hash_text

_REASON_CODES = {
    "insufficient_evidence",
    "wrong_citation",
    "policy_override",
    "other",
}


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    trace_id: str
    dataset_id: str | None
    item_id: str | None
    question_hash: str
    initial_label: str
    initial_answer_hash: str
    final_label: str
    override: bool
    time_to_decision_ms: int
    reason_code: str
    provenance_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "dataset_id": self.dataset_id,
            "item_id": self.item_id,
            "question_hash": self.question_hash,
            "initial_label": self.initial_label,
            "initial_answer_hash": self.initial_answer_hash,
            "final_label": self.final_label,
            "override": self.override,
            "time_to_decision_ms": self.time_to_decision_ms,
            "reason_code": self.reason_code,
            "provenance_hash": self.provenance_hash,
        }


def decision_template(
    *,
    trace_id: str,
    dataset_id: str | None,
    item_id: str | None,
    question_hash: str,
    initial_label: str,
    initial_answer: str,
    provenance_hash: str,
) -> dict[str, object]:
    """Build a deterministic HITL template that operators can fill."""

    return {
        "trace_id": str(trace_id or ""),
        "dataset_id": str(dataset_id or "") or None,
        "item_id": str(item_id or "") or None,
        "question_hash": str(question_hash or ""),
        "initial_label": str(initial_label or ""),
        "initial_answer_hash": hash_text(str(initial_answer or "")),
        "final_label": str(initial_label or ""),
        "override": False,
        "time_to_decision_ms": 0,
        "reason_code": "other",
        "provenance_hash": str(provenance_hash or ""),
    }


def _as_str(value: object | None) -> str:
    return str(value or "").strip()


def _as_bool(value: object | None) -> bool:
    if isinstance(value, bool):
        return value
    raw = _as_str(value).lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _as_int(value: object | None) -> int:
    if isinstance(value, int):
        return value
    raw = _as_str(value)
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def parse_decision_event(data: Mapping[str, object]) -> DecisionEvent:
    trace_id = _as_str(data.get("trace_id"))
    question_hash = _as_str(data.get("question_hash"))
    initial_label = _as_str(data.get("initial_label"))
    initial_answer_hash = _as_str(data.get("initial_answer_hash"))
    final_label = _as_str(data.get("final_label"))
    reason_code = _as_str(data.get("reason_code")) or "other"
    provenance_hash = _as_str(data.get("provenance_hash"))
    override = _as_bool(data.get("override"))
    time_to_decision_ms = max(0, _as_int(data.get("time_to_decision_ms")))

    if not trace_id:
        raise ValueError("trace_id is required")
    if not question_hash:
        raise ValueError("question_hash is required")
    if not initial_label:
        raise ValueError("initial_label is required")
    if not initial_answer_hash:
        raise ValueError("initial_answer_hash is required")
    if not final_label:
        raise ValueError("final_label is required")
    if reason_code not in _REASON_CODES:
        raise ValueError(f"reason_code must be one of: {', '.join(sorted(_REASON_CODES))}")
    if not provenance_hash:
        raise ValueError("provenance_hash is required")

    dataset_id = _as_str(data.get("dataset_id")) or None
    item_id = _as_str(data.get("item_id")) or None
    return DecisionEvent(
        trace_id=trace_id,
        dataset_id=dataset_id,
        item_id=item_id,
        question_hash=question_hash,
        initial_label=initial_label,
        initial_answer_hash=initial_answer_hash,
        final_label=final_label,
        override=override,
        time_to_decision_ms=time_to_decision_ms,
        reason_code=reason_code,
        provenance_hash=provenance_hash,
    )


def _iter_event_files(directory: Path) -> Sequence[Path]:
    return sorted(
        [
            path
            for path in directory.rglob("*.json")
            if path.is_file()
        ],
        key=lambda p: str(p).lower(),
    )


def ingest_hitl_directory(directory: Path) -> dict[str, object]:
    directory = directory.resolve()
    if not directory.exists() or not directory.is_dir():
        raise ValueError(f"HITL template directory not found: {directory}")

    events: list[DecisionEvent] = []
    for path in _iter_event_files(directory):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"Invalid HITL payload (expected object): {path}")
        event = parse_decision_event(payload)
        events.append(event)
        ledger.append_fact("hitl_decision", event.to_dict())

    overrides = sum(1 for event in events if event.override)
    durations = [event.time_to_decision_ms for event in events]
    reason_counts: dict[str, int] = {}
    for event in events:
        reason_counts[event.reason_code] = reason_counts.get(event.reason_code, 0) + 1

    sorted_reasons = sorted(reason_counts.items(), key=lambda row: (-row[1], row[0]))
    return {
        "ingested_events": len(events),
        "override_rate": (overrides / len(events)) if events else 0.0,
        "avg_time_to_decision_ms": mean(durations) if durations else 0.0,
        "top_reason_codes": [
            {"reason_code": code, "count": count} for code, count in sorted_reasons
        ],
        "source_dir": str(directory),
        "ledger_path": str(ledger.current_log_path()),
    }


__all__ = [
    "DecisionEvent",
    "decision_template",
    "ingest_hitl_directory",
    "parse_decision_event",
]

