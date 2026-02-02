from __future__ import annotations

"""Heuristic label inference for evaluation fallbacks.

The primary RAG/eval path expects structured labels from the LLM JSON contract.
This module exists only as a defensive fallback when a provider returns plain
text or malformed JSON.
"""

LABEL_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "prohibited",
        [
            "is prohibited",
            "are prohibited",
            "not permitted",
            "cannot export",
            "ban",
            "prohibited export",
        ],
    ),
    (
        "license_required",
        [
            "license is required",
            "requires a license",
            "must obtain a license",
            "license needed",
            "license before exporting",
        ],
    ),
    (
        "permitted_with_license",
        [
            "permitted with a license",
            "allowed with a license",
            "allowed under license",
            "license exception tmp",
            "export can proceed once a license",
        ],
    ),
    (
        "no_license_required",
        [
            "no license is required",
            "does not require a license",
            "without a license to a country group b destination",
        ],
    ),
    (
        "permitted",
        [
            "can export",
            "is permitted",
            "allowed to export",
            "export can proceed",
            "authorized to export",
        ],
    ),
    (
        "unanswerable",
        [
            "cannot be answered",
            "not enough information",
            "insufficient information",
            "outside the covered export regulations",
            "decline to answer",
            "no basis to answer",
        ],
    ),
]


def infer_label(answer: str) -> str:
    normalized = (answer or "").strip().lower()
    if not normalized:
        return "unanswerable"
    for label, patterns in LABEL_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return label
    return "unknown"


__all__ = ["infer_label", "LABEL_PATTERNS"]
