from pathlib import Path
import json
from rdflib import RDF, Graph, URIRef
from rdflib.namespace import RDFS
from .ontology import EAR_NS, DCT, graph_with_prefixes, safe_literal


def export_triples(
    data_dir: Path = Path("data"),
    out_ttl: Path = Path("kg/ear_triples.ttl"),
) -> None:
    out_ttl.parent.mkdir(parents=True, exist_ok=True)
    with out_ttl.open("w", encoding="utf-8") as f:
        f.write(Path("kg/ear_ontology.ttl").read_text())
        for source in ("ear", "nsf"):
            fn = data_dir / f"{source}_corpus.jsonl"
            if not fn.exists():
                continue
            for line in fn.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                rec = json.loads(line)
                pid = rec["identifier"].replace(":", "_")
                f.write(f"\nex:paragraph_{pid} a ex:Paragraph ;\n")
                escaped_text = rec["text"].replace('"', '\\"')
                f.write(f'    ex:hasText """{escaped_text}""" ;\n')
                if source == "ear":
                    part = rec["identifier"].split(":")[0]
                    f.write(f'    ex:part "{part}" ;\n')
                f.write("\n")
                for ent in rec.get("entities", {}).get("orgs", []):
                    eid = ent.replace(" ", "_")
                    f.write(f"ex:paragraph_{pid} ex:mentions ex:entity_{eid} .\n")
                    f.write(f"ex:entity_{eid} a ex:Entity ; rdfs:label \"{ent}\" .\n")



def emit_tradegov_entities(records: list[dict[str, str]], out_dir: Path) -> tuple[Path, int]:
    """Write Trade.gov entity records to Turtle in ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "tradegov.ttl"
    g = graph_with_prefixes()
    for rec in records:
        ent_iri = EAR_NS[f"entity/{rec['id']}"]
        g.add((ent_iri, RDF.type, EAR_NS.Entity))
        g.add((ent_iri, RDFS.label, safe_literal(rec["name"])))
        country = rec.get("country")
        if country:
            g.add((ent_iri, EAR_NS.country, safe_literal(country)))
        src = rec.get("source_url")
        if src:
            g.add((ent_iri, DCT.source, URIRef(src)))
    _write_sorted_ttl(g, out_path)
    return out_path, len(g)


def _write_sorted_ttl(graph: Graph, out_path: Path) -> None:
    prefixes = sorted(graph.namespace_manager.namespaces(), key=lambda x: x[0])
    lines: list[str] = []
    nm = graph.namespace_manager
    for s, p, o in graph:
        lines.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} .")
    lines.sort()
    with out_path.open("w", encoding="utf-8") as f:
        for prefix, ns in prefixes:
            f.write(f"@prefix {prefix}: <{ns}> .\n")
        f.write("\n")
        for line in lines:
            f.write(line + "\n")
