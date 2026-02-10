from __future__ import annotations

"""Registry of SPARQL sanity check queries.

Each query is a deterministic ``SELECT`` that returns offending nodes.  The
keys in :data:`QUERIES` are sorted to provide stable output ordering.
"""

from collections.abc import Iterable

# Query strings are defined with compact prefixes for readability.
QUERIES: dict[str, str] = {
    "orphan_sections": """
PREFIX ear: <https://ear.example.org/schema#>
SELECT ?section WHERE {
  ?section a ear:Section .
  FILTER NOT EXISTS { ?reg a ear:Reg ; ear:hasSection ?section . }
}
""".strip(),
    "orphan_paragraphs": """
PREFIX ear: <https://ear.example.org/schema#>
SELECT ?para WHERE {
  ?para a ear:Paragraph .
  FILTER NOT EXISTS { ?sec a ear:Section ; ear:hasParagraph ?para . }
}
""".strip(),
    "missing_provenance": """
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX ear: <https://ear.example.org/schema#>
SELECT ?para WHERE {
  ?para a ear:Paragraph .
  FILTER (
    NOT EXISTS { ?para dct:source ?s } ||
    NOT EXISTS { ?para prov:wasDerivedFrom ?d } ||
    NOT EXISTS { ?para dct:issued ?date }
  )
}
""".strip(),
    "dangling_citations": """
PREFIX ear: <https://ear.example.org/schema#>
SELECT ?cit WHERE {
  ?cit a ear:Citation .
  FILTER NOT EXISTS { ?p a ear:Paragraph ; ear:cites ?cit . }
}
""".strip(),
    "entity_mentions_without_type": """
PREFIX ear: <https://ear.example.org/schema#>
PREFIX ent: <https://ear.example.org/entity/>
SELECT ?n WHERE {
  ?n ?p ?o .
  FILTER(STRSTARTS(STR(?n), "https://ear.example.org/entity/")) .
  FILTER NOT EXISTS { ?n a ear:Entity . }
}
""".strip(),
}


def iter_queries() -> Iterable[tuple[str, str]]:
    """Yield ``(name, query)`` pairs in a deterministic order."""

    for name in sorted(QUERIES):
        yield name, QUERIES[name]


__all__ = ["QUERIES", "iter_queries"]
