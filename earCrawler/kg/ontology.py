"""Minimal ontology helpers for knowledge graph emitters."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import rdflib
from rdflib import Graph, Literal, Namespace

EAR_NS = Namespace("https://example.org/ear#")
ENT_NS = Namespace("https://example.org/entity#")
DCT = Namespace("http://purl.org/dc/terms/")
PROV = Namespace("http://www.w3.org/ns/prov#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")


def graph_with_prefixes(*, identifier: rdflib.term.Identifier | None = None) -> Graph:
    """Return a graph pre-bound with common prefixes.

    Parameters
    ----------
    identifier:
        Optional identifier for the graph. When provided the returned
        :class:`~rdflib.Graph` will use this value as its named graph IRI.
    """

    g = Graph(identifier=identifier)
    g.bind("ear", EAR_NS)
    g.bind("ent", ENT_NS)
    g.bind("dct", DCT)
    g.bind("prov", PROV)
    g.bind("xsd", XSD)
    return g


def iri_for_paragraph(hash_hex: str) -> rdflib.term.Identifier:
    """Return deterministic paragraph IRI based on a SHA256 hex digest."""

    return EAR_NS[f"p_{hash_hex[:16]}"]


def iri_for_section(sec_id: str) -> rdflib.term.Identifier:
    """Normalise a section identifier like ``734.3`` to ``ear:s_734_3``."""

    norm = sec_id.strip().replace(".", "_")
    return EAR_NS[f"s_{norm}"]


def safe_literal(
    value: str | date | datetime,
    datatype: Optional[rdflib.term.Identifier] = None,
) -> Literal:
    """Create a literal for ``value`` with sensible defaults.

    ``datetime`` and ``date`` values are converted to ISO format with the
    appropriate XSD datatype unless one is explicitly provided.
    """

    if isinstance(value, datetime):
        dt = datatype or XSD.dateTime
        return Literal(value.isoformat(), datatype=dt)
    if isinstance(value, date):
        dt = datatype or XSD.date
        return Literal(value.isoformat(), datatype=dt)
    return Literal(value, datatype=datatype)


__all__ = [
    "EAR_NS",
    "ENT_NS",
    "graph_with_prefixes",
    "iri_for_paragraph",
    "iri_for_section",
    "safe_literal",
    "DCT",
    "PROV",
    "XSD",
]

