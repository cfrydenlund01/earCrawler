from pathlib import Path
import json
from urllib.parse import quote
from rdflib import RDF, Graph, URIRef, Namespace
from rdflib.namespace import RDFS
from .ontology import EAR_NS, DCT, graph_with_prefixes, safe_literal
from .iri import entity_iri
from .namespaces import RESOURCE_NS
from .prov import add_provenance


def export_triples(
    data_dir: Path = Path("data"),
    out_ttl: Path = Path("kg/ear_triples.ttl"),
) -> None:
    out_ttl.parent.mkdir(parents=True, exist_ok=True)
    g = graph_with_prefixes()
    ex_ns = Namespace(f"{RESOURCE_NS}legacy/ear/")
    g.namespace_manager.bind("ex", ex_ns, replace=True)
    for source in ("ear", "nsf"):
        fn = data_dir / f"{source}_corpus.jsonl"
        if not fn.exists():
            continue
        for line in fn.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            rec = json.loads(line)
            identifier = str(rec.get("identifier", "")).strip()
            if not identifier:
                continue
            pid = identifier.replace(":", "_")
            paragraph_iri = ex_ns[f"paragraph_{pid}"]
            g.add((paragraph_iri, RDF.type, ex_ns.Paragraph))
            text_value = rec.get("text", "")
            if text_value:
                g.add((paragraph_iri, ex_ns.hasText, safe_literal(text_value)))
            if source == "ear":
                part = identifier.split(":", 1)[0]
                if part:
                    g.add((paragraph_iri, ex_ns.part, safe_literal(part)))
            entities = rec.get("entities", {}).get("orgs", []) or []
            for entity_name in entities:
                slug = quote(entity_name.strip() or "entity", safe="").lower()
                ent_iri = ex_ns[f"entity_{slug}"]
                g.add((paragraph_iri, ex_ns.mentions, ent_iri))
                g.add((ent_iri, RDF.type, ex_ns.Entity))
                g.add((ent_iri, RDFS.label, safe_literal(entity_name)))
    prefix_text = ""
    schema = Path("kg/ear_ontology.ttl")
    if schema.exists():
        prefix_text = schema.read_text(encoding="utf-8")
    _write_sorted_ttl(g, out_ttl, prefix_text=prefix_text)


def emit_tradegov_entities(
    records: list[dict[str, str]], out_dir: Path, prov_graph: Graph | None = None
) -> tuple[Path, int]:
    """Write Trade.gov entity records to Turtle in ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "tradegov.ttl"
    g = graph_with_prefixes()
    for rec in records:
        ent_iri = URIRef(entity_iri(rec["id"]))
        g.add((ent_iri, RDF.type, EAR_NS.Entity))
        g.add((ent_iri, RDFS.label, safe_literal(rec["name"])))
        country = rec.get("country")
        if country:
            g.add((ent_iri, EAR_NS.country, safe_literal(country)))
        src = rec.get("source_url")
        if src:
            g.add((ent_iri, DCT.source, URIRef(src)))
            if prov_graph is not None:
                add_provenance(
                    prov_graph,
                    ent_iri,
                    source_url=src,
                    provider_domain="trade.gov",
                    request_url=src,
                    generated_at=rec.get("date"),
                    response_sha256=rec.get("sha256"),
                )
    _write_sorted_ttl(g, out_path)
    return out_path, len(g)


def _write_sorted_ttl(graph: Graph, out_path: Path, *, prefix_text: str = "") -> None:
    prefixes = sorted(graph.namespace_manager.namespaces(), key=lambda x: x[0])
    lines: list[str] = []
    nm = graph.namespace_manager
    for s, p, o in graph:
        lines.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} .")
    lines.sort()
    with out_path.open("w", encoding="utf-8") as f:
        if prefix_text:
            f.write(prefix_text)
            if not prefix_text.endswith("\n"):
                f.write("\n")
        for prefix, ns in prefixes:
            f.write(f"@prefix {prefix}: <{ns}> .\n")
        f.write("\n")
        for line in lines:
            f.write(line + "\n")
