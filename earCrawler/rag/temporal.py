from __future__ import annotations

"""Explicit temporal reasoning helpers for as-of retrieval and refusal behavior."""

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable, Mapping, Sequence

from earCrawler.rag.corpus_contract import normalize_ear_section_id

_ISO_DATE_RE = re.compile(r"\b(?P<value>\d{4}-\d{2}-\d{2})\b")
_TEMPORAL_CANDIDATE_MULTIPLIER = 4
_TEMPORAL_MIN_CANDIDATES = 12


def normalize_iso_date(value: object | None) -> str | None:
    """Return a canonical ISO date when ``value`` is parseable, else ``None``."""

    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            try:
                return date.fromisoformat(raw).isoformat()
            except ValueError:
                return None
    return None


def extract_iso_dates(text: object | None) -> list[str]:
    """Return distinct ISO dates in first-seen order."""

    seen: set[str] = set()
    values: list[str] = []
    for match in _ISO_DATE_RE.finditer(str(text or "")):
        normalized = normalize_iso_date(match.group("value"))
        if normalized and normalized not in seen:
            seen.add(normalized)
            values.append(normalized)
    return values


def temporal_candidate_count(top_k: int) -> int:
    requested = max(1, int(top_k))
    return max(_TEMPORAL_MIN_CANDIDATES, requested * _TEMPORAL_CANDIDATE_MULTIPLIER)


def infer_snapshot_date(
    *,
    snapshot_date: object | None = None,
    source_ref: object | None = None,
    snapshot_id: object | None = None,
) -> str | None:
    """Infer a snapshot date from explicit ISO date tokens only."""

    explicit = normalize_iso_date(snapshot_date)
    if explicit:
        return explicit
    for candidate in (source_ref, snapshot_id):
        matches = extract_iso_dates(candidate)
        if matches:
            return matches[0]
    return None


def apply_version_suffix(doc_id: str, version_suffix: str | None) -> str:
    """Attach a version suffix while preserving existing paragraph suffixes."""

    normalized_doc_id = str(doc_id or "").strip()
    suffix = str(version_suffix or "").strip()
    if not normalized_doc_id or not suffix:
        return normalized_doc_id
    if "#" not in normalized_doc_id:
        return f"{normalized_doc_id}#{suffix}"
    left, right = normalized_doc_id.split("#", 1)
    if right == suffix or right.startswith(f"{suffix}:"):
        return normalized_doc_id
    return f"{left}#{suffix}:{right}"


@dataclass(frozen=True)
class TemporalRequest:
    requested: bool
    effective_date: str | None
    source: str | None
    question_dates: tuple[str, ...]
    refusal_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "effective_date": self.effective_date,
            "source": self.source,
            "question_dates": list(self.question_dates),
            "refusal_reason": self.refusal_reason,
        }


@dataclass(frozen=True)
class TemporalSelection:
    request: TemporalRequest
    selected_docs: tuple[dict[str, object], ...]
    applicable_count: int
    future_count: int
    expired_count: int
    superseded_count: int
    unknown_count: int
    refusal_reason: str | None = None

    @property
    def should_refuse(self) -> bool:
        return bool(self.request.refusal_reason or self.refusal_reason)

    def to_dict(self) -> dict[str, object]:
        return {
            **self.request.to_dict(),
            "selected_count": len(self.selected_docs),
            "applicable_count": self.applicable_count,
            "future_count": self.future_count,
            "expired_count": self.expired_count,
            "superseded_count": self.superseded_count,
            "unknown_count": self.unknown_count,
            "should_refuse": self.should_refuse,
            "refusal_reason": self.request.refusal_reason or self.refusal_reason,
        }


def resolve_temporal_request(
    question: str,
    *,
    effective_date: str | None = None,
) -> TemporalRequest:
    """Resolve an explicit as-of date from the request or question text."""

    question_dates = tuple(extract_iso_dates(question))
    explicit_date = normalize_iso_date(effective_date)
    if effective_date is not None and explicit_date is None:
        raise ValueError("effective_date must be an ISO date in YYYY-MM-DD format")

    if explicit_date:
        conflicts = [value for value in question_dates if value != explicit_date]
        return TemporalRequest(
            requested=True,
            effective_date=explicit_date,
            source="parameter",
            question_dates=question_dates,
            refusal_reason="conflicting_effective_dates" if conflicts else None,
        )

    if len(question_dates) > 1:
        return TemporalRequest(
            requested=True,
            effective_date=None,
            source="question",
            question_dates=question_dates,
            refusal_reason="multiple_dates_in_question",
        )

    if len(question_dates) == 1:
        return TemporalRequest(
            requested=True,
            effective_date=question_dates[0],
            source="question",
            question_dates=question_dates,
        )

    return TemporalRequest(
        requested=False,
        effective_date=None,
        source=None,
        question_dates=question_dates,
    )


def _doc_metadata(doc: Mapping[str, object]) -> Mapping[str, object]:
    raw = doc.get("raw")
    if isinstance(raw, Mapping):
        return raw
    return doc


def _doc_section_id(doc: Mapping[str, object]) -> str | None:
    raw = _doc_metadata(doc)
    for key in ("section_id", "section", "doc_id", "id", "entity_id"):
        normalized = normalize_ear_section_id(raw.get(key))
        if normalized:
            return normalized
    for key in ("section_id", "section", "doc_id", "id", "entity_id"):
        normalized = normalize_ear_section_id(doc.get(key))
        if normalized:
            return normalized
    return None


def _doc_temporal_fields(doc: Mapping[str, object]) -> tuple[str | None, str | None, str | None]:
    raw = _doc_metadata(doc)
    effective_from = normalize_iso_date(
        raw.get("effective_from") or raw.get("effective_date")
    )
    effective_to = normalize_iso_date(
        raw.get("effective_to") or raw.get("expires_on") or raw.get("superseded_on")
    )
    snapshot_date = infer_snapshot_date(
        snapshot_date=raw.get("snapshot_date"),
        source_ref=raw.get("source_ref"),
        snapshot_id=raw.get("snapshot_id"),
    )
    return effective_from, effective_to, snapshot_date


def _annotate_doc(doc: Mapping[str, object], **fields: object) -> dict[str, object]:
    annotated = dict(doc)
    raw = _doc_metadata(doc)
    if raw is not doc:
        annotated["raw"] = dict(raw)
    for key, value in fields.items():
        if value is not None:
            annotated[key] = value
    return annotated


def select_temporal_documents(
    docs: Sequence[Mapping[str, object]],
    *,
    request: TemporalRequest,
    top_k: int,
) -> TemporalSelection:
    """Select docs applicable to ``request.effective_date`` or refuse conservatively."""

    if request.refusal_reason:
        return TemporalSelection(
            request=request,
            selected_docs=tuple(),
            applicable_count=0,
            future_count=0,
            expired_count=0,
            superseded_count=0,
            unknown_count=0,
            refusal_reason=request.refusal_reason,
        )

    if not request.requested or not request.effective_date:
        return TemporalSelection(
            request=request,
            selected_docs=tuple(dict(doc) for doc in docs[: max(1, int(top_k))]),
            applicable_count=len(docs[: max(1, int(top_k))]),
            future_count=0,
            expired_count=0,
            superseded_count=0,
            unknown_count=0,
        )

    as_of = date.fromisoformat(request.effective_date)
    section_versions: dict[str, list[str]] = {}
    for doc in docs:
        section_id = _doc_section_id(doc)
        _effective_from, _effective_to, snapshot_date = _doc_temporal_fields(doc)
        if section_id and snapshot_date:
            section_versions.setdefault(section_id, []).append(snapshot_date)
    latest_snapshot_per_section: dict[str, str] = {}
    for section_id, values in section_versions.items():
        applicable = sorted({value for value in values if value <= request.effective_date})
        if applicable:
            latest_snapshot_per_section[section_id] = applicable[-1]

    selected: list[dict[str, object]] = []
    counts = {
        "applicable": 0,
        "future": 0,
        "expired": 0,
        "superseded": 0,
        "unknown": 0,
    }

    for doc in docs:
        section_id = _doc_section_id(doc)
        effective_from, effective_to, snapshot_date = _doc_temporal_fields(doc)
        status = "unknown"
        reason = "no_temporal_metadata"

        if effective_from or effective_to:
            if effective_from and as_of < date.fromisoformat(effective_from):
                status = "future"
                reason = "effective_from_after_query_date"
            elif effective_to and as_of > date.fromisoformat(effective_to):
                status = "expired"
                reason = "effective_to_before_query_date"
            else:
                status = "applicable"
                reason = "within_effective_window"
        elif section_id and snapshot_date:
            chosen_snapshot = latest_snapshot_per_section.get(section_id)
            if chosen_snapshot is None:
                status = "future"
                reason = "no_snapshot_at_or_before_query_date"
            elif snapshot_date == chosen_snapshot:
                status = "applicable"
                reason = "latest_snapshot_at_or_before_query_date"
            elif snapshot_date > request.effective_date:
                status = "future"
                reason = "snapshot_after_query_date"
            else:
                status = "superseded"
                reason = "older_snapshot_superseded_for_query_date"

        counts[status] += 1
        annotated = _annotate_doc(
            doc,
            temporal_status=status,
            temporal_reason=reason,
            effective_from=effective_from,
            effective_to=effective_to,
            snapshot_date=snapshot_date,
        )
        if status == "applicable":
            selected.append(annotated)

    refusal_reason = None
    if not selected:
        refusal_reason = (
            "temporal_evidence_ambiguous"
            if counts["unknown"] > 0
            else "no_temporally_applicable_evidence"
        )

    return TemporalSelection(
        request=request,
        selected_docs=tuple(selected[: max(1, int(top_k))]),
        applicable_count=counts["applicable"],
        future_count=counts["future"],
        expired_count=counts["expired"],
        superseded_count=counts["superseded"],
        unknown_count=counts["unknown"],
        refusal_reason=refusal_reason,
    )


__all__ = [
    "TemporalRequest",
    "TemporalSelection",
    "apply_version_suffix",
    "extract_iso_dates",
    "infer_snapshot_date",
    "normalize_iso_date",
    "resolve_temporal_request",
    "select_temporal_documents",
    "temporal_candidate_count",
]
