"""Load Consolidated Screening List entities into Fuseki."""
from __future__ import annotations

import hashlib
import json
from typing import Callable, Iterable

from api_clients import search_entities
from earCrawler.kg.jena_client import JenaClient
from earCrawler.kg.provenance_store import ProvenanceRecorder
from earCrawler.transforms import CanonicalRegistry
from earCrawler.transforms.csl_to_rdf import entity_iri, to_bindings

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
    registry: CanonicalRegistry | None = None,
    provenance: ProvenanceRecorder | None = None,
    search_fn: Callable[..., Iterable[dict]] | None = None,
) -> int:
    """Fetch entities for ``query`` and load them into Fuseki."""

    client = jena or JenaClient()
    registry = registry or CanonicalRegistry()
    prov = provenance or ProvenanceRecorder()
    search_fn = search_fn or search_entities
    results = search_fn(query, size=limit, sources=list(sources) if sources else None)
    count = 0
    for record in results:
        canonical = registry.canonical_entity(record)
        source_url = (
            canonical.get("source_url")
            or record.get("source_url")
            or record.get("source_list_url")
            or record.get("url")
            or ""
        )
        retrieved_at = (
            canonical.get("retrieved_at")
            or record.get("retrieved_at")
            or record.get("updated_at")
            or record.get("date_updated")
        )
        request_url = canonical.get("request_url") or record.get("request_url") or source_url
        bindings = to_bindings(canonical)
        payload = {
            "id": bindings["id"],
            "name": bindings["name"],
            "country": bindings["country"],
            "programs": bindings["programs"],
            "source": bindings["source"],
        }
        content_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        subject = registry.resolve_deprecated(entity_iri({"id": bindings["id"]}))
        changed = prov.record(
            subject,
            source_url=source_url,
            provider_domain="trade.gov",
            content_hash=content_hash,
            retrieved_at=retrieved_at,
            request_url=request_url,
        )
        if changed:
            upsert_entity(client, bindings)
            count += 1
    prov.flush()
    return count


__all__ = ["load_csl_by_query", "upsert_entity"]
