from __future__ import annotations

"""Shared strict validator for RAG LLM JSON outputs.

This module enforces a machine-checkable, grounded contract:
- fixed top-level keys only (no extras)
- correct types and required keys present
- enums constrained to allowed labels
- citations contain verbatim quotes, and at least one quote must be a substring
  of the retrieved context for non-unanswerable labels
- optional justification strings are accepted to support explainability during eval
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

DEFAULT_ALLOWED_LABELS: Set[str] = {
    "license_required",
    "no_license_required",
    "exception_applies",
    "permitted_with_license",
    "permitted",
    "prohibited",
    "unanswerable",
    "true",
    "false",
}

TRUTHINESS_LABELS: Set[str] = {"true", "false", "unanswerable"}

_REQUIRED_KEYS: Set[str] = {"answer_text", "label", "justification"}
_MAX_RAW_PREVIEW = 400


@dataclass
class OutputSchemaError(ValueError):
    code: str
    message: str
    raw_text: str | None = None
    details: dict | None = None

    def __str__(self) -> str:  # pragma: no cover - delegated to ValueError repr
        return self.message

    def as_dict(self) -> Dict[str, object]:
        preview = None
        raw_len = 0
        if self.raw_text is not None:
            raw_len = len(self.raw_text)
            preview = self.raw_text[:_MAX_RAW_PREVIEW]
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
            "raw_preview": preview,
            "raw_len": raw_len,
        }


_NEW_REQUIRED_KEYS: Set[str] = {
    "label",
    "answer_text",
    "citations",
    "evidence_okay",
    "assumptions",
}
_NEW_OPTIONAL_KEYS: Set[str] = {"justification"}

_CITATION_REQUIRED_KEYS: Set[str] = {"section_id", "quote"}
_CITATION_ALLOWED_KEYS: Set[str] = {"section_id", "quote", "span_id", "source"}

_EVIDENCE_REQUIRED_KEYS: Set[str] = {"ok", "reasons"}

_REFUSAL_KEYWORDS = re.compile(
    r"\b(insufficient|not enough|cannot determine|unable to determine|unanswerable)\b",
    flags=re.IGNORECASE,
)
_HINT_KEYWORDS = re.compile(r"\b(need|missing|provide)\b", flags=re.IGNORECASE)


def _coerce_str(parsed: dict, key: str, *, raw: str) -> str:
    value = parsed.get(key)
    if not isinstance(value, str):
        raise OutputSchemaError(
            code="wrong_type",
            message=f"{key} must be a string",
            raw_text=raw,
            details={"key": key, "expected": "string", "actual": type(value).__name__},
        )
    value = value.strip()
    if not value:
        raise OutputSchemaError(
            code="invalid_value",
            message=f"{key} must be a non-empty string",
            raw_text=raw,
            details={"key": key},
        )
    return value


def _normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _substring_in_context(quote: str, context: str) -> bool:
    q = _normalize_ws(quote)
    c = _normalize_ws(context)
    if not q or not c:
        return False
    return q in c


def parse_strict_answer_json(
    raw: str,
    *,
    allowed_labels: Iterable[str],
    context: str | None = None,
) -> Dict[str, object]:
    """Parse and validate strict JSON RAG answer payloads.

    Expected schema (no extra keys):
    {
      "label": "<one of allowed_labels>",
      "answer_text": "<non-empty string>",
      "citations": [{"section_id": "...", "quote": "...", "span_id": "..."}],
      "evidence_okay": {"ok": true, "reasons": ["..."]},
      "assumptions": ["..."]
    }
    """

    allowed = set(allowed_labels)
    if not isinstance(raw, str):
        raise OutputSchemaError(
            code="invalid_json",
            message="LLM output must be a JSON string",
            raw_text=None,
            details={"expected": "string"},
        )
    raw_str = raw.strip()
    if not raw_str:
        raise OutputSchemaError(
            code="invalid_json",
            message="LLM output is empty",
            raw_text=raw,
            details={"reason": "empty"},
        )
    try:
        parsed = json.loads(raw_str)
    except json.JSONDecodeError as exc:
        raise OutputSchemaError(
            code="invalid_json",
            message=f"LLM output is not valid JSON: {exc.msg}",
            raw_text=raw,
            details={"pos": exc.pos},
        ) from None

    if not isinstance(parsed, dict):
        raise OutputSchemaError(
            code="wrong_type",
            message="Top-level JSON must be an object",
            raw_text=raw,
            details={"expected": "object", "actual": type(parsed).__name__},
        )

    allowed_top_level = _NEW_REQUIRED_KEYS | _NEW_OPTIONAL_KEYS
    extras = sorted(set(parsed.keys()) - allowed_top_level)
    if extras:
        raise OutputSchemaError(
            code="extra_key",
            message=f"Unexpected key: {extras[0]}",
            raw_text=raw,
            details={"unexpected": extras[0]},
        )
    missing = sorted(_NEW_REQUIRED_KEYS - set(parsed.keys()))
    if missing:
        raise OutputSchemaError(
            code="missing_key",
            message=f"Missing required key: {missing[0]}",
            raw_text=raw,
            details={"missing": missing},
        )

    label_value = _coerce_str(parsed, "label", raw=raw).lower()
    answer_text = _coerce_str(parsed, "answer_text", raw=raw)

    if label_value not in allowed:
        raise OutputSchemaError(
            code="invalid_enum",
            message=f"label '{label_value}' is not allowed",
            raw_text=raw,
            details={"allowed": sorted(allowed), "label": label_value},
        )

    justification = None
    if "justification" in parsed:
        justification = _coerce_str(parsed, "justification", raw=raw)

    citations = parsed.get("citations")
    if not isinstance(citations, list):
        raise OutputSchemaError(
            code="wrong_type",
            message="citations must be an array",
            raw_text=raw,
            details={"key": "citations", "expected": "array", "actual": type(citations).__name__},
        )

    parsed_citations: List[dict] = []
    matched_any_quote = False
    for idx, item in enumerate(citations):
        if not isinstance(item, dict):
            raise OutputSchemaError(
                code="wrong_type",
                message="citation must be an object",
                raw_text=raw,
                details={"key": "citations", "index": idx, "expected": "object", "actual": type(item).__name__},
            )
        item_extras = sorted(set(item.keys()) - _CITATION_ALLOWED_KEYS)
        if item_extras:
            raise OutputSchemaError(
                code="extra_key",
                message=f"Unexpected citation key: {item_extras[0]}",
                raw_text=raw,
                details={"key": "citations", "index": idx, "unexpected": item_extras[0]},
            )
        item_missing = sorted(_CITATION_REQUIRED_KEYS - set(item.keys()))
        if item_missing:
            raise OutputSchemaError(
                code="missing_key",
                message=f"Missing required citation key: {item_missing[0]}",
                raw_text=raw,
                details={"key": "citations", "index": idx, "missing": item_missing},
            )
        section_id = _coerce_str(item, "section_id", raw=raw)
        quote = _coerce_str(item, "quote", raw=raw)
        span_id = item.get("span_id")
        if span_id is not None and not isinstance(span_id, str):
            raise OutputSchemaError(
                code="wrong_type",
                message="span_id must be a string when provided",
                raw_text=raw,
                details={"key": "citations", "index": idx, "field": "span_id", "expected": "string"},
            )
        if context is not None and _substring_in_context(quote, context):
            matched_any_quote = True
        parsed_citations.append(
            {"section_id": section_id, "quote": quote, "span_id": span_id}
        )

    evidence_okay = parsed.get("evidence_okay")
    if not isinstance(evidence_okay, dict):
        raise OutputSchemaError(
            code="wrong_type",
            message="evidence_okay must be an object",
            raw_text=raw,
            details={"key": "evidence_okay", "expected": "object", "actual": type(evidence_okay).__name__},
        )
    evidence_extras = sorted(set(evidence_okay.keys()) - _EVIDENCE_REQUIRED_KEYS)
    if evidence_extras:
        raise OutputSchemaError(
            code="extra_key",
            message=f"Unexpected evidence_okay key: {evidence_extras[0]}",
            raw_text=raw,
            details={"key": "evidence_okay", "unexpected": evidence_extras[0]},
        )
    evidence_missing = sorted(_EVIDENCE_REQUIRED_KEYS - set(evidence_okay.keys()))
    if evidence_missing:
        raise OutputSchemaError(
            code="missing_key",
            message=f"Missing required evidence_okay key: {evidence_missing[0]}",
            raw_text=raw,
            details={"key": "evidence_okay", "missing": evidence_missing},
        )
    ok = evidence_okay.get("ok")
    reasons = evidence_okay.get("reasons")
    if not isinstance(ok, bool):
        raise OutputSchemaError(
            code="wrong_type",
            message="evidence_okay.ok must be a boolean",
            raw_text=raw,
            details={"key": "evidence_okay.ok", "expected": "boolean", "actual": type(ok).__name__},
        )
    if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
        raise OutputSchemaError(
            code="wrong_type",
            message="evidence_okay.reasons must be an array of strings",
            raw_text=raw,
            details={"key": "evidence_okay.reasons"},
        )
    if ok is False:
        # Caller requested hard rejection when model flags evidence as not OK.
        raise OutputSchemaError(
            code="evidence_not_ok",
            message="Model reported evidence_okay.ok=false",
            raw_text=raw,
            details={"reasons": reasons},
        )

    assumptions = parsed.get("assumptions")
    if not isinstance(assumptions, list) or not all(isinstance(a, str) for a in assumptions):
        raise OutputSchemaError(
            code="wrong_type",
            message="assumptions must be an array of strings",
            raw_text=raw,
            details={"key": "assumptions"},
        )

    if context is not None and assumptions:
        unsupported = [a for a in assumptions if not _substring_in_context(a, context)]
        if unsupported and label_value != "unanswerable":
            raise OutputSchemaError(
                code="assumption_unsupported",
                message="Assumptions are not supported by retrieved context; must label unanswerable",
                raw_text=raw,
                details={"unsupported": unsupported},
            )

    if context is not None and (label_value != "unanswerable") and not matched_any_quote:
        raise OutputSchemaError(
            code="ungrounded_citation",
            message="No citation quote is a substring of retrieved context; must label unanswerable",
            raw_text=raw,
            details={"matched_quotes": 0},
        )

    if label_value == "unanswerable":
        # Enforce a refusal + retrieval-guidance hint.
        if not _REFUSAL_KEYWORDS.search(answer_text) or not _HINT_KEYWORDS.search(answer_text):
            raise OutputSchemaError(
                code="invalid_value",
                message="unanswerable answer_text must include a short refusal and a retrieval-guidance hint",
                raw_text=raw,
                details={"label": label_value},
            )
        lowered = answer_text.strip().lower()
        if lowered.startswith("yes") or lowered.startswith("no"):
            raise OutputSchemaError(
                code="invalid_value",
                message="unanswerable answer_text must not assert a yes/no outcome",
                raw_text=raw,
                details={"label": label_value},
            )

    return {
        "label": label_value,
        "answer_text": answer_text,
        "justification": justification,
        "citations": parsed_citations,
        "evidence_okay": {"ok": ok, "reasons": list(reasons)},
        "assumptions": list(assumptions),
        "matched_any_quote": matched_any_quote,
    }


__all__ = [
    "DEFAULT_ALLOWED_LABELS",
    "TRUTHINESS_LABELS",
    "OutputSchemaError",
    "parse_strict_answer_json",
]
