from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from earCrawler.rag.pipeline import _normalize_section_id

DEFAULT_PHASE2_GATES_PATH = (
    Path(__file__).resolve().parents[2] / "eval" / "phase2_groundedness_gates.json"
)

_SECTION_BLOCK_RE = re.compile(r"(?:\A|\n\n)\[(?P<section>[^\]]+)\]\s*", flags=re.DOTALL)
_SECTION_INLINE_RE = re.compile(
    r"\bEAR-\d[\w().-]*|\b\d{3}\.\d+(?:\([^)]+\))*",
    flags=re.IGNORECASE,
)
_CLAIM_SPLIT_RE = re.compile(
    r"\s*(?:[;!?]+|\.(?=\s|$)|\bbut\b|\bhowever\b|\byet\b|,\s*not\b)\s*",
    flags=re.IGNORECASE,
)
_LEADING_VERDICT_RE = re.compile(r"^(?:yes|no|true|false)\b[:,]?\s*", flags=re.IGNORECASE)
_HEDGE_RE = re.compile(
    r"\b("
    r"may|might|could|can depend|depends|dependent|unclear|uncertain|"
    r"insufficient (?:info|information|evidence)|not enough (?:info|information|evidence)|"
    r"cannot determine|unable to determine|cannot answer|unanswerable|need more|need additional|"
    r"if provided|if more information"
    r")\b",
    flags=re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "all",
        "an",
        "and",
        "answer",
        "any",
        "are",
        "as",
        "at",
        "be",
        "before",
        "by",
        "can",
        "cited",
        "conclusion",
        "context",
        "described",
        "does",
        "excerpt",
        "for",
        "from",
        "in",
        "is",
        "it",
        "its",
        "of",
        "or",
        "provision",
        "question",
        "section",
        "states",
        "stated",
        "that",
        "the",
        "their",
        "them",
        "these",
        "they",
        "this",
        "those",
        "under",
        "when",
        "with",
    }
)


@dataclass(frozen=True)
class Phase2GateThresholds:
    unanswerable_accuracy_min: float
    grounding_contract_pass_rate_min: float
    citation_precision_eq: float
    known_bad_citations_count_eq: int
    valid_citation_rate_eq: float
    supported_rate_eq: float
    overclaim_rate_eq: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "unanswerable_accuracy_min": self.unanswerable_accuracy_min,
            "grounding_contract_pass_rate_min": self.grounding_contract_pass_rate_min,
            "citation_precision_eq": self.citation_precision_eq,
            "known_bad_citations_count_eq": self.known_bad_citations_count_eq,
            "valid_citation_rate_eq": self.valid_citation_rate_eq,
            "supported_rate_eq": self.supported_rate_eq,
            "overclaim_rate_eq": self.overclaim_rate_eq,
        }


def load_phase2_gate_thresholds(path: Path | None = None) -> Phase2GateThresholds:
    raw = json.loads((path or DEFAULT_PHASE2_GATES_PATH).read_text(encoding="utf-8"))
    payload = raw.get("golden_phase2") if isinstance(raw, Mapping) else {}
    if not isinstance(payload, Mapping):
        raise ValueError("phase2 groundedness gate config must contain a golden_phase2 object")
    return Phase2GateThresholds(
        unanswerable_accuracy_min=float(payload.get("unanswerable_accuracy_min", 0.9)),
        grounding_contract_pass_rate_min=float(
            payload.get("grounding_contract_pass_rate_min", 0.8)
        ),
        citation_precision_eq=float(payload.get("citation_precision_eq", 1.0)),
        known_bad_citations_count_eq=int(payload.get("known_bad_citations_count_eq", 0)),
        valid_citation_rate_eq=float(payload.get("valid_citation_rate_eq", 1.0)),
        supported_rate_eq=float(payload.get("supported_rate_eq", 1.0)),
        overclaim_rate_eq=float(payload.get("overclaim_rate_eq", 0.0)),
    )


def _normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _substring_in_context(quote: str, context: str) -> bool:
    q = _normalize_ws(quote)
    c = _normalize_ws(context)
    return bool(q and c and q in c)


def _expand_context_string(context: str) -> list[str]:
    if not context:
        return []
    matches = list(_SECTION_BLOCK_RE.finditer(context))
    if not matches:
        return [context]

    entries: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        if start > 0:
            leading = context[:start].strip()
            if leading:
                entries.append(leading)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(context)
        block = context[match.start():end].strip()
        if block:
            entries.append(block)
    return entries


def _build_context_index(result: Mapping[str, object]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    raw_context = str(result.get("raw_context") or "").strip()
    for entry in _expand_context_string(raw_context):
        text = str(entry or "").strip()
        if not text:
            continue
        match = re.match(r"^\[(?P<section>[^\]]+)\]\s*(?P<text>.*)$", text, flags=re.DOTALL)
        if not match:
            continue
        section_id = _normalize_section_id(match.group("section"))
        section_text = str(match.group("text") or "").strip()
        if section_id and section_text:
            index.setdefault(section_id, []).append(section_text)

    for doc in result.get("retrieved_docs") or []:
        if not isinstance(doc, Mapping):
            continue
        section_id = _normalize_section_id(doc.get("section") or doc.get("id"))
        text = str(doc.get("text") or "").strip()
        if section_id and text:
            index.setdefault(section_id, []).append(text)
    return index


def _normalize_token(token: str) -> str:
    value = token.lower()
    if len(value) > 5 and value.endswith("ing"):
        value = value[:-3]
    elif len(value) > 4 and value.endswith("ies"):
        value = value[:-3] + "y"
    elif len(value) > 4 and value.endswith("ed"):
        value = value[:-2]
    elif len(value) > 4 and value.endswith("es"):
        value = value[:-2]
    elif len(value) > 4 and value.endswith("s") and not value.endswith("ss"):
        value = value[:-1]
    return value


def _content_tokens(text: str) -> set[str]:
    scrubbed = _SECTION_INLINE_RE.sub(" ", str(text or "").lower())
    tokens = {
        _normalize_token(token)
        for token in _WORD_RE.findall(scrubbed)
        if token not in _STOPWORDS and len(token) > 1
    }
    return {token for token in tokens if token}


def _extract_section_mentions(text: str) -> set[str]:
    mentions: set[str] = set()
    for raw in _SECTION_INLINE_RE.findall(str(text or "")):
        candidate = raw if raw.upper().startswith("EAR-") else f"EAR-{raw}"
        norm = _normalize_section_id(candidate)
        if norm:
            mentions.add(norm)
    return mentions


def _truncate_snippet(text: str, *, limit: int = 120) -> str:
    cleaned = _normalize_ws(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _extract_claims(answer_text: str) -> list[dict[str, object]]:
    claims: list[dict[str, object]] = []
    normalized_answer = _normalize_ws(answer_text).replace("U.S.", "US").replace("U.S", "US")
    for raw in _CLAIM_SPLIT_RE.split(normalized_answer):
        claim = _LEADING_VERDICT_RE.sub("", str(raw or "")).strip(" ,:")
        if not claim:
            continue
        decisive = not bool(_HEDGE_RE.search(claim))
        claims.append(
            {
                "text": claim,
                "decisive": decisive,
                "tokens": _content_tokens(claim),
                "section_mentions": _extract_section_mentions(claim),
            }
        )
    return claims


def evaluate_groundedness_signals(
    result: Mapping[str, object],
    reference_sections: set[str] | None = None,
) -> dict[str, object]:
    citations = result.get("citations") or []
    context_index = _build_context_index(result)
    citation_details: list[dict[str, object]] = []
    validity_reasons: set[str] = set()
    valid_citations = 0

    for idx, raw_citation in enumerate(citations):
        citation = raw_citation if isinstance(raw_citation, Mapping) else {}
        raw_section_id = str(citation.get("section_id") or "").strip()
        quote = str(citation.get("quote") or "").strip()
        section_id = _normalize_section_id(raw_section_id)
        valid = True
        reasons: list[str] = []

        if not raw_section_id or not section_id or raw_section_id != section_id:
            valid = False
            reasons.append("invalid_section_id")
        if not quote:
            valid = False
            reasons.append("quote_missing")
        if valid and reference_sections is not None and section_id not in reference_sections:
            valid = False
            reasons.append("section_not_in_references")

        quote_in_section = False
        if section_id and quote:
            section_contexts = context_index.get(section_id, [])
            if section_contexts:
                quote_in_section = any(
                    _substring_in_context(quote, section_context)
                    for section_context in section_contexts
                )
                if not quote_in_section:
                    reasons.append("quote_not_in_section_context")
            else:
                reasons.append("section_context_missing")

        if valid:
            valid_citations += 1
        validity_reasons.update(reasons)
        citation_details.append(
            {
                "index": idx,
                "section_id": section_id,
                "quote": quote,
                "valid": valid,
                "quote_in_section": quote_in_section,
                "quote_tokens": sorted(_content_tokens(quote)),
                "reasons": sorted(set(reasons)),
            }
        )

    claims = _extract_claims(str(result.get("answer_text") or result.get("answer") or ""))
    label = str(result.get("label") or "").strip().lower()
    decisive_claims = [] if label == "unanswerable" else [claim for claim in claims if bool(claim.get("decisive"))]
    supported_claims = 0
    overclaim_snippets: list[str] = []
    claim_checks: list[dict[str, object]] = []

    for claim in decisive_claims:
        claim_text = str(claim.get("text") or "")
        claim_tokens = set(claim.get("tokens") or set())
        mentioned_sections = set(claim.get("section_mentions") or set())
        linked_supported: list[dict[str, object]] = []
        linked_unsupported = False

        for citation in citation_details:
            section_id = citation.get("section_id")
            if not section_id:
                continue
            quote_tokens = set(citation.get("quote_tokens") or set())
            overlap = claim_tokens & quote_tokens
            explicitly_mentions_section = bool(section_id in mentioned_sections)
            if explicitly_mentions_section or overlap:
                if bool(citation.get("valid")) and bool(citation.get("quote_in_section")):
                    linked_supported.append(citation)
                else:
                    linked_unsupported = True

        reasons: list[str] = []
        supported = False
        if linked_supported:
            if mentioned_sections & {
                str(citation.get("section_id"))
                for citation in linked_supported
                if citation.get("section_id")
            }:
                supported = True
                reasons.append("supported_by_explicit_section_reference")
            else:
                union_quote_tokens: set[str] = set()
                for citation in linked_supported:
                    union_quote_tokens.update(set(citation.get("quote_tokens") or set()))
                overlap = claim_tokens & union_quote_tokens
                min_overlap = 1 if len(claim_tokens) <= 2 else 2
                coverage = (len(overlap) / len(claim_tokens)) if claim_tokens else 0.0
                supported = bool(claim_tokens) and (
                    len(overlap) >= min_overlap or coverage >= 0.5
                )
                reasons.append(
                    "supported_by_section_quote"
                    if supported
                    else "claim_not_supported_by_quote"
                )
        elif linked_unsupported:
            reasons.append("claim_linked_citation_not_supported")
        else:
            reasons.append("claim_without_linked_citation")

        if supported:
            supported_claims += 1
        else:
            overclaim_snippets.append(_truncate_snippet(claim_text))

        claim_checks.append(
            {
                "claim": claim_text,
                "supported": supported,
                "reasons": reasons,
                "citation_indices": [int(citation["index"]) for citation in linked_supported],
                "citation_sections": [
                    str(citation.get("section_id"))
                    for citation in linked_supported
                    if citation.get("section_id")
                ],
            }
        )

    total_citations = len(citation_details)
    total_claims = len(decisive_claims)
    overclaim_count = len(overclaim_snippets)
    valid_citation_rate = (valid_citations / total_citations) if total_citations else 1.0
    supported_rate = (supported_claims / total_claims) if total_claims else 1.0
    overclaim_rate = (overclaim_count / total_claims) if total_claims else 0.0

    citation_validity = {
        "ok": valid_citation_rate == 1.0,
        "valid_citations": valid_citations,
        "total_citations": total_citations,
        "valid_citation_rate": valid_citation_rate,
        "reasons": sorted(validity_reasons),
        "details": citation_details,
    }
    citation_support = {
        "supported": supported_rate == 1.0,
        "supported_claims": supported_claims,
        "total_claims": total_claims,
        "supported_rate": supported_rate,
        "reasons": sorted(
            {
                reason
                for claim_check in claim_checks
                for reason in claim_check.get("reasons") or []
                if reason != "supported_by_explicit_section_reference"
            }
        ),
        "claims": claim_checks,
    }
    overclaim = {
        "ok": overclaim_count == 0,
        "overclaim_count": overclaim_count,
        "overclaim_rate": overclaim_rate,
        "snippets": overclaim_snippets[:5],
    }

    errors = sorted(
        set(citation_validity["reasons"])
        | set(citation_support["reasons"])
        | ({"overclaim_present"} if overclaim_count else set())
    )

    return {
        "ok": bool(citation_validity["ok"] and citation_support["supported"] and overclaim["ok"]),
        "errors": errors,
        "citation_validity": citation_validity,
        "citation_support": citation_support,
        "overclaim": overclaim,
        "counts": {
            "items": 1,
            "items_with_citations": 1 if total_citations else 0,
            "total_citations": total_citations,
            "valid_citations": valid_citations,
            "total_claims": total_claims,
            "supported_claims": supported_claims,
            "overclaim_count": overclaim_count,
            "items_overclaim": 1 if overclaim_count else 0,
        },
    }


def finalize_groundedness_metrics(
    counts: Mapping[str, int],
    num_items: int,
) -> dict[str, object]:
    total_citations = counts.get("total_citations", 0) or 0
    items_with_citations = counts.get("items_with_citations", 0) or 0
    valid_citations = counts.get("valid_citations", 0) or 0
    total_claims = counts.get("total_claims", 0) or 0
    supported_claims = counts.get("supported_claims", 0) or 0
    overclaim_count = counts.get("overclaim_count", 0) or 0
    items_overclaim = counts.get("items_overclaim", 0) or 0

    presence_rate = items_with_citations / num_items if num_items else 0.0
    valid_citation_rate = valid_citations / total_citations if total_citations else 1.0
    supported_rate = supported_claims / total_claims if total_claims else 1.0
    overclaim_rate = overclaim_count / total_claims if total_claims else 0.0

    return {
        "presence_rate": presence_rate,
        "valid_citation_rate": valid_citation_rate,
        "valid_id_rate": valid_citation_rate,
        "supported_rate": supported_rate,
        "overclaim_rate": overclaim_rate,
        "counts": {
            "items_with_citations": items_with_citations,
            "total_citations": total_citations,
            "valid_citations": valid_citations,
            "total_claims": total_claims,
            "supported_claims": supported_claims,
            "overclaim_count": overclaim_count,
            "items_overclaim": items_overclaim,
        },
    }


__all__ = [
    "DEFAULT_PHASE2_GATES_PATH",
    "Phase2GateThresholds",
    "evaluate_groundedness_signals",
    "finalize_groundedness_metrics",
    "load_phase2_gate_thresholds",
]
