"""Emitter for EAR corpus JSONL to deterministic Turtle."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
import hashlib
from api_clients.federalregister_client import FederalRegisterClient

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
from .iri import resource_iri
from .prov import add_provenance


def fetch_ear_corpus(
    term_or_citation: str,
    client: FederalRegisterClient | None = None,
    out_dir: Path = Path("kg/source/ear"),
) -> Path:
    """Fetch EAR articles and write normalized JSONL."""
    client = client or FederalRegisterClient()
    articles = client.get_ear_articles(term_or_citation, per_page=1)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ear_corpus.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for art in articles:
            sha = hashlib.sha256(art["text"].encode("utf-8")).hexdigest()
            rec = {
                "sha256": sha,
                "source_url": art["source_url"],
                "date": art["publication_date"],
                "id": art["id"],
                "section": "1",
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_path


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


def emit_ear(
    in_dir: Path, out_dir: Path, prov_graph: Graph | None = None
) -> tuple[Path, int]:
    """Emit EAR JSONL from ``in_dir`` to Turtle in ``out_dir``.

    Returns a tuple of output path and triple count.
    """

    in_path = in_dir / "ear_corpus.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ear.ttl"

    g = graph_with_prefixes()
    reg_iri = URIRef(resource_iri("ear", "reg"))
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
            date_str = rec.get("date")
            if source:
                if _is_url(source):
                    g.add((para_iri, DCT.source, URIRef(source)))
                else:
                    g.add((para_iri, DCT.source, safe_literal(source)))
                if prov_graph is not None:
                    add_provenance(
                        prov_graph,
                        para_iri,
                        source_url=source,
                        provider_domain="federalregister.gov",
                        request_url=source,
                        generated_at=date_str,
                        response_sha256=para_hash,
                    )
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
