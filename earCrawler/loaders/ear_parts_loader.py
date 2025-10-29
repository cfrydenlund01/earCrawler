"""Loader utilities for EAR parts derived from Federal Register content."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Callable, Iterable, Sequence, Set

from api_clients import search_documents
from earCrawler.kg.anchors import Anchor, AnchorIndex
from earCrawler.kg.jena_client import JenaClient
from earCrawler.kg.provenance_store import ProvenanceRecorder
from earCrawler.transforms.ear_fr_to_rdf import extract_parts_from_text, pick_parts

PART_TEMPLATE_PATH = "earCrawler/sparql/upsert_part.sparql"
PART_ANCHOR_TEMPLATE_PATH = "earCrawler/sparql/upsert_part_anchor.sparql"


def upsert_part(jena: JenaClient, part_no: str) -> None:
    """Ensure the given part number exists as an EAR Part node."""

    with open(PART_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
        template = handle.read()
    query = template.replace("__PARTNO__", part_no)
    jena.update(query)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def _anchor_identifier(part_no: str, anchor: Anchor) -> str:
    raw = f"{part_no}:{anchor.document_id}:{anchor.title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def upsert_part_anchor(jena: JenaClient, part_no: str, anchor: Anchor) -> None:
    """Insert/update an anchor node linked to ``part_no``."""

    anchor_id = _anchor_identifier(part_no, anchor)
    with open(PART_ANCHOR_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
        template = handle.read()
    query = (
        template
        .replace("__PARTNO__", part_no)
        .replace("__ANCHOR_ID__", anchor_id)
        .replace("__DOC_ID__", _escape(anchor.document_id))
        .replace("__TITLE__", _escape(anchor.title))
        .replace("__SOURCE__", _escape(anchor.source_url))
        .replace("__SNIPPET__", _escape(anchor.snippet))
    )
    jena.update(query)


def link_entity_to_part(jena: JenaClient, entity_id: str, part_no: str) -> None:
    """Materialise a relationship between an entity and a part."""

    normalized_id = entity_id.replace(" ", "_")
    update = f"""
PREFIX ear:  <https://ear.example.org/schema#>
PREFIX ent:  <https://ear.example.org/entity/>
PREFIX part: <https://ear.example.org/part/>
INSERT DATA {{
  ent:{normalized_id} ear:mentionedInPart part:{part_no} .
}}
"""
    jena.update(update)


def load_parts_from_fr(
    term: str,
    *,
    jena: JenaClient | None = None,
    pages: int = 1,
    per_page: int = 20,
    provenance: ProvenanceRecorder | None = None,
    anchor_index: AnchorIndex | None = None,
    search_fn: Callable[..., dict] | None = None,
) -> Set[str]:
    """Search the Federal Register for ``term`` and upsert referenced parts."""

    client = jena or JenaClient()
    prov = provenance or ProvenanceRecorder()
    anchors = anchor_index or AnchorIndex()
    search_fn = search_fn or search_documents
    discovered: Set[str] = set()
    part_hits: dict[str, list[Anchor]] = defaultdict(list)
    for page in range(1, pages + 1):
        payload = search_fn(term, per_page=per_page, page=page)
        results: Sequence[dict] = payload.get("results", payload or [])
        for record in results:
            doc_id = str(record.get("document_number") or record.get("id") or "")
            if not doc_id:
                doc_id = f"doc-{page}-{len(part_hits)}"
            snippets = [
                record.get("title", ""),
                record.get("abstract", "") or "",
            ]
            excerpts = record.get("excerpts") or []
            if isinstance(excerpts, list):
                snippets.extend(excerpts)
            text = " ".join(filter(None, snippets))
            parts = extract_parts_from_text(text)
            if not parts:
                continue
            snippet = " ".join(text.split())[:280]
            anchor = Anchor(
                document_id=doc_id,
                title=record.get("title", ""),
                source_url=record.get("html_url") or record.get("url") or "",
                snippet=snippet,
                publication_date=record.get("publication_date"),
            )
            for part in parts:
                part_hits[part].append(anchor)
            discovered.update(parts)

    for part, hits in part_hits.items():
        sorted_hits = sorted(hits, key=lambda a: (a.document_id, a.title.lower()))
        anchors.update_part(part, sorted_hits)
        payload = [
            {
                "doc": a.document_id,
                "url": a.source_url,
                "snippet": a.snippet,
                "pub": a.publication_date,
            }
            for a in sorted_hits
        ]
        content_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        first = sorted_hits[0] if sorted_hits else None
        changed = prov.record(
            f"https://ear.example.org/part/{part}",
            source_url=(first.source_url if first else ""),
            provider_domain="federalregister.gov",
            content_hash=content_hash,
            retrieved_at=first.publication_date if first else None,
            request_url=first.source_url if first else None,
        )
        if changed:
            upsert_part(client, part)
            for anchor in sorted_hits:
                upsert_part_anchor(client, part, anchor)

    anchors.flush()
    prov.flush()
    return set(pick_parts(discovered))


def link_entities_to_parts_by_name_contains(
    jena: JenaClient,
    name_contains: str,
    parts: Iterable[str],
) -> int:
    """Link all entities whose name contains ``name_contains`` to given parts."""

    parts_list = pick_parts(parts)
    if not parts_list:
        return 0

    select = f"""
PREFIX ear: <https://ear.example.org/schema#>
SELECT ?id ?name WHERE {{
  ?id a ear:Entity ;
      ear:name ?name .
  FILTER CONTAINS(LCASE(?name), LCASE("{name_contains}"))
}}
"""
    response = jena.select(select)
    rows = response.get("results", {}).get("bindings", [])
    link_count = 0
    for row in rows:
        value = row["id"]["value"]
        curie = value.rsplit("/", 1)[-1]
        for part in parts_list:
            link_entity_to_part(jena, curie, part)
            link_count += 1
    return link_count


__all__ = [
    "link_entities_to_parts_by_name_contains",
    "link_entity_to_part",
    "load_parts_from_fr",
    "upsert_part",
    "upsert_part_anchor",
]
