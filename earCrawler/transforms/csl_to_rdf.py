"""Helpers to map Consolidated Screening List records onto our EAR schema."""
from __future__ import annotations

from typing import Any, Dict

BASE = "https://ear.example.org/"


def _slugify(value: str) -> str:
    """Return a conservative slug made safe for CURIE style identifiers."""

    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "entity"


def entity_iri(entity: Dict[str, Any]) -> str:
    """Compute an entity IRI, preferring deterministic identifiers."""

    identifier = (
        entity.get("id")
        or entity.get("entity_number")
        or entity.get("name", "unknown")
    )
    return f"{BASE}entity/{_slugify(str(identifier))}"


def to_bindings(entity: Dict[str, Any]) -> dict:
    """Return template bindings for the SPARQL upsert template."""

    name = (entity.get("name") or "").replace('"', "'")
    addresses = entity.get("addresses") or [{}]
    primary = addresses[0] if isinstance(addresses, list) and addresses else {}
    country = primary.get("country") or entity.get("country") or ""
    programs_source = entity.get("programs") or entity.get("source_list_url") or []
    programs = ",".join(programs_source)
    identifier = (
        entity.get("id")
        or entity.get("entity_number")
        or name
        or "entity"
    )
    return {
        "id": str(identifier),
        "name": name,
        "country": str(country),
        "programs": programs,
        "source": entity.get("source", "CSL"),
    }


__all__ = ["BASE", "entity_iri", "to_bindings"]
