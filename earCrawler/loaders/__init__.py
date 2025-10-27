"""Public loaders for populating the knowledge graph."""

from .csl_loader import load_csl_by_query, upsert_entity  # noqa: F401
from .ear_parts_loader import (  # noqa: F401
    link_entities_to_parts_by_name_contains,
    link_entity_to_part,
    load_parts_from_fr,
    upsert_part,
)

__all__ = [
    "link_entities_to_parts_by_name_contains",
    "link_entity_to_part",
    "load_csl_by_query",
    "load_parts_from_fr",
    "upsert_entity",
    "upsert_part",
]
