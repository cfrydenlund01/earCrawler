from __future__ import annotations

"""Canonical IRI builders and legacy-IRI canonicalization.

These helpers are deterministic, idempotent, and safe to apply to stored
snapshots or dataset references.
"""

import re
from urllib.parse import quote

from .namespaces import ENTITY_NS, GRAPH_NS, RESOURCE_NS, SCHEMA_NS

_EAR_SECTION_RE = re.compile(
    r"^(?:15\s*CFR\s*)?(?P<section>\d{3}(?:\.\S+)?)$",
    re.IGNORECASE,
)


def canonical_section_id(value: object | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.upper().startswith("EAR-"):
        if "#" in raw:
            raw = raw.split("#", 1)[0].strip()
        return raw
    match = _EAR_SECTION_RE.match(raw)
    if match:
        return f"EAR-{match.group('section')}"
    return raw


def _quote_segment(value: str) -> str:
    # Encode everything outside RFC3986 unreserved characters to keep IRIs
    # stable across serializers and downstream consumers.
    return quote(value, safe="-._~_")


def section_iri(section_id: str) -> str:
    canonical = canonical_section_id(section_id) or str(section_id).strip()
    return f"{RESOURCE_NS}ear/section/{_quote_segment(canonical)}"


def paragraph_iri(sha256_hex: str) -> str:
    digest = str(sha256_hex).strip()
    if not digest:
        raise ValueError("sha256_hex must be non-empty")
    return f"{RESOURCE_NS}ear/paragraph/{digest[:16]}"


def entity_iri(entity_id: str) -> str:
    raw = str(entity_id).strip()
    if not raw:
        raise ValueError("entity_id must be non-empty")
    norm = raw.replace(" ", "_")
    return f"{ENTITY_NS}{_quote_segment(norm)}"


def resource_iri(*segments: str) -> str:
    segs = [str(s).strip().strip("/") for s in segments if str(s).strip()]
    if not segs:
        raise ValueError("resource_iri requires at least one segment")
    encoded = "/".join(_quote_segment(s) for s in segs)
    return f"{RESOURCE_NS}{encoded}"


def graph_iri(snapshot_digest: str, *, kind: str = "kg") -> str:
    digest = str(snapshot_digest).strip()
    if not digest:
        raise ValueError("snapshot_digest must be non-empty")
    return f"{GRAPH_NS}{_quote_segment(kind)}/{_quote_segment(digest)}"


def canonicalize_iri(iri: str) -> str:
    """Rewrite a legacy IRI into the canonical namespace (best effort).

    Idempotent: passing a canonical IRI returns it unchanged.
    """

    raw = str(iri or "").strip()
    if not raw:
        return raw

    if raw.startswith(RESOURCE_NS) or raw.startswith(ENTITY_NS) or raw.startswith(GRAPH_NS):
        return raw
    if raw.startswith(SCHEMA_NS):
        return raw

    legacy_ear = "https://example.org/ear#"
    if raw.startswith(legacy_ear):
        frag = raw[len(legacy_ear) :]
        if frag == "reg":
            return resource_iri("ear", "reg")
        if frag.startswith("p_"):
            return paragraph_iri(frag.removeprefix("p_"))
        if frag.startswith("s_"):
            sec = frag.removeprefix("s_").replace("_", ".")
            return section_iri(sec)
        if frag.startswith("entity/"):
            return entity_iri(frag.removeprefix("entity/"))
        if "/" in frag:
            # policy/obligation/exception/prov resources use path-like fragments.
            return resource_iri("ear", *[p for p in frag.split("/") if p])
        # Otherwise treat as a schema/ontology term (class, predicate, shape id, etc.).
        return f"{SCHEMA_NS}{frag}"

    legacy_ent = "https://example.org/entity#"
    if raw.startswith(legacy_ent):
        frag = raw[len(legacy_ent) :]
        if frag == "Entity" or frag.endswith("Shape"):
            return f"{SCHEMA_NS}{frag}"
        # Preserve the deterministic legacy IDs while moving to the canonical entity namespace.
        return entity_iri(frag)

    # Leave unknown IRIs unchanged.
    return raw


__all__ = [
    "canonical_section_id",
    "section_iri",
    "paragraph_iri",
    "entity_iri",
    "resource_iri",
    "graph_iri",
    "canonicalize_iri",
]
