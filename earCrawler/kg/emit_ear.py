"""Emitter for EAR corpus JSONL to deterministic Turtle."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from rdflib import RDF, Graph, URIRef

from .ontology import (
    EAR_NS,
    DCT,
    PROV,
    graph_with_prefixes,
    iri_for_paragraph,
    iri_for_section,
    safe_literal,
)


def _is_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


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


def emit_ear(in_dir: Path, out_dir: Path) -> tuple[Path, int]:
    """Emit EAR JSONL from ``in_dir`` to Turtle in ``out_dir``.

    Returns a tuple of output path and triple count.
    """

    in_path = in_dir / "ear_corpus.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ear.ttl"

    g = graph_with_prefixes()
    reg_iri = EAR_NS["reg"]
    g.add((reg_iri, RDF.type, EAR_NS.Reg))

    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            para_hash = rec.get("sha256")
            if not para_hash:
                continue
            para_iri = iri_for_paragraph(para_hash)
            g.add((para_iri, RDF.type, EAR_NS.Paragraph))
            source = rec.get("source_url")
            if source:
                if _is_url(source):
                    g.add((para_iri, DCT.source, URIRef(source)))
                else:
                    g.add((para_iri, DCT.source, safe_literal(source)))
            date_str = rec.get("date")
            if date_str:
                try:
                    d = date.fromisoformat(date_str)
                    g.add((para_iri, DCT.issued, safe_literal(d)))
                except Exception:
                    g.add((para_iri, DCT.issued, safe_literal(date_str)))
            rec_id = rec.get("id")
            if rec_id is not None:
                g.add((para_iri, PROV.wasDerivedFrom, safe_literal(str(rec_id))))
            sec_id = rec.get("section")
            if sec_id:
                sec_iri = iri_for_section(str(sec_id))
                g.add((sec_iri, RDF.type, EAR_NS.Section))
                g.add((reg_iri, EAR_NS.hasSection, sec_iri))
                g.add((sec_iri, EAR_NS.hasParagraph, para_iri))
            else:
                g.add((reg_iri, EAR_NS.hasParagraph, para_iri))

    _write_sorted_ttl(g, out_path)
    return out_path, len(g)


__all__ = ["emit_ear"]

