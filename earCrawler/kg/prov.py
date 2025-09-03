from __future__ import annotations

"""Helpers for PROV-O provenance with deterministic IRIs."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Dict, Optional

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, FOAF

from .ontology import EAR_NS, DCT, PROV, XSD, graph_with_prefixes, safe_literal

PROV_GRAPH_IRI = URIRef("urn:graph:prov")


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def new_prov_graph() -> Graph:
    """Return a graph for provenance quads in ``urn:graph:prov``."""
    g = graph_with_prefixes(identifier=PROV_GRAPH_IRI)
    g.bind("foaf", FOAF)
    return g


def mint_agent(domain: str) -> URIRef:
    norm = domain.replace("http://", "").replace("https://", "").strip("/")
    norm = norm.replace(".", "_")
    return EAR_NS[f"agent/{norm}"]


def mint_activity(request_url: str, params: Optional[Dict[str, str]] = None) -> URIRef:
    key = request_url
    if params:
        parts = [f"{k}={v}" for k, v in sorted(params.items())]
        key += "?" + "&".join(parts)
    digest = _hash(key)[:16]
    return EAR_NS[f"activity/{digest}"]


def mint_request(request_url: str, params: Optional[Dict[str, str]] = None) -> URIRef:
    key = request_url
    if params:
        parts = [f"{k}={v}" for k, v in sorted(params.items())]
        key += "?" + "&".join(parts)
    digest = _hash("req:" + key)[:16]
    return EAR_NS[f"request/{digest}"]


def add_provenance(
    g: Graph,
    entity_iri: URIRef,
    *,
    source_url: str,
    provider_domain: str,
    request_url: Optional[str] = None,
    params: Optional[Dict[str, str]] = None,
    generated_at: Optional[datetime | str] = None,
    response_sha256: Optional[str] = None,
) -> None:
    """Append provenance quads for ``entity_iri`` to graph ``g``."""

    req_url = request_url or source_url
    agent = mint_agent(provider_domain)
    activity = mint_activity(req_url, params)
    request = mint_request(req_url, params)

    if isinstance(generated_at, str):
        ts = generated_at
    else:
        gtime = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        ts = gtime.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    g.add((entity_iri, RDF.type, PROV.Entity))
    g.add((entity_iri, PROV.wasDerivedFrom, URIRef(source_url)))
    g.add((entity_iri, PROV.wasGeneratedBy, activity))
    g.add((entity_iri, PROV.wasAttributedTo, agent))
    g.add((entity_iri, PROV.generatedAtTime, Literal(ts, datatype=XSD.dateTime)))

    g.add((activity, RDF.type, PROV.Activity))
    g.add((activity, PROV.used, request))
    g.add((activity, PROV.wasAssociatedWith, agent))
    if response_sha256:
        g.add((activity, EAR_NS.responseHash, safe_literal(response_sha256)))

    g.add((request, RDF.type, PROV.Entity))
    g.add((request, DCT.source, URIRef(req_url)))

    g.add((agent, RDF.type, PROV.Agent))
    g.add((agent, FOAF.homepage, URIRef(f"https://{provider_domain}")))


def write_prov_files(graph: Graph, out_dir) -> None:
    """Serialize provenance graph to TTL and N-Quads with sorted statements."""
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ttl_path = out_dir / "prov.ttl"
    nq_path = out_dir / "prov.nq"

    prefixes = sorted(graph.namespace_manager.namespaces(), key=lambda x: x[0])
    nm = graph.namespace_manager
    ttl_lines = []
    nq_lines = []
    ctx = PROV_GRAPH_IRI.n3(nm)
    for s, p, o in graph:
        ttl_lines.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} .")
        nq_lines.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} {ctx} .")
    ttl_lines.sort()
    nq_lines.sort()

    with ttl_path.open("w", encoding="utf-8") as f:
        for prefix, ns in prefixes:
            f.write(f"@prefix {prefix}: <{ns}> .\n")
        f.write("\n")
        for line in ttl_lines:
            f.write(line + "\n")

    with nq_path.open("w", encoding="utf-8") as f:
        for line in nq_lines:
            f.write(line + "\n")

__all__ = [
    "new_prov_graph",
    "add_provenance",
    "write_prov_files",
    "mint_agent",
    "mint_activity",
    "mint_request",
    "PROV_GRAPH_IRI",
]
