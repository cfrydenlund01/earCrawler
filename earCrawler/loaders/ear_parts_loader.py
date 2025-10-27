"""Loader utilities for EAR parts derived from Federal Register content."""
from __future__ import annotations

from typing import Iterable, Sequence, Set

from earCrawler.api_clients import search_documents
from earCrawler.kg.jena_client import JenaClient
from earCrawler.transforms.ear_fr_to_rdf import extract_parts_from_text, pick_parts

PART_TEMPLATE_PATH = "earCrawler/sparql/upsert_part.sparql"


def upsert_part(jena: JenaClient, part_no: str) -> None:
    """Ensure the given part number exists as an EAR Part node."""

    with open(PART_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
        template = handle.read()
    query = template.replace("__PARTNO__", part_no)
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
) -> Set[str]:
    """Search the Federal Register for ``term`` and upsert referenced parts."""

    client = jena or JenaClient()
    discovered: Set[str] = set()
    for page in range(1, pages + 1):
        payload = search_documents(term, per_page=per_page, page=page)
        results: Sequence[dict] = payload.get("results", payload or [])
        for record in results:
            snippets = [
                record.get("title", ""),
                record.get("abstract", "") or "",
            ]
            excerpts = record.get("excerpts") or []
            if isinstance(excerpts, list):
                snippets.extend(excerpts)
            text = " ".join(filter(None, snippets))
            parts = extract_parts_from_text(text)
            for part in parts:
                upsert_part(client, part)
            discovered.update(parts)
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
]
