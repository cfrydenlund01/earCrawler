"""Load Consolidated Screening List entities into Fuseki."""
from __future__ import annotations

from typing import Iterable

from api_clients import search_entities
from earCrawler.kg.jena_client import JenaClient
from earCrawler.transforms.csl_to_rdf import to_bindings

ENTITY_TEMPLATE_PATH = "earCrawler/sparql/upsert_entity.sparql"


def upsert_entity(jena: JenaClient, bindings: dict) -> None:
    """Upsert a single entity into Fuseki using the SPARQL template."""

    with open(ENTITY_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
        template = handle.read()
    # id placeholder is reused for CURIE and literal; keep literal replacements afterwards
    query = template.replace("__ID__", bindings["id"].replace(" ", "_"))
    query = (
        query
        .replace("__NAME__", bindings["name"])
        .replace("__SOURCE__", bindings["source"])
        .replace("__PROGRAMS__", bindings["programs"])
        .replace("__COUNTRY__", bindings["country"])
    )
    jena.update(query)


def load_csl_by_query(
    query: str,
    *,
    limit: int = 25,
    sources: Iterable[str] | None = None,
    jena: JenaClient | None = None,
) -> int:
    """Fetch entities for ``query`` and load them into Fuseki."""

    client = jena or JenaClient()
    results = search_entities(query, size=limit, sources=list(sources) if sources else None)
    count = 0
    for record in results:
        bindings = to_bindings(record)
        upsert_entity(client, bindings)
        count += 1
    return count


__all__ = ["load_csl_by_query", "upsert_entity"]
