from __future__ import annotations

from pathlib import Path

from rdflib import RDF, Graph, URIRef

from earCrawler.corpus import build_corpus, validate_corpus
from earCrawler.kg.emit_ear import emit_ear
from earCrawler.kg.emit_nsf import _iri_for_entity, emit_nsf
from earCrawler.kg.ontology import EAR_NS
from earCrawler.kg.validate import validate_files


def test_supported_path_semantic_contract(tmp_path: Path) -> None:
    fixtures = Path("tests/fixtures")
    data_dir = tmp_path / "data"
    kg_dir = tmp_path / "kg"

    # 1) Supported corpus build path.
    manifest = build_corpus(["ear", "nsf"], data_dir, live=False, fixtures=fixtures)
    assert manifest["summary"]["ear"] > 0
    assert manifest["summary"]["nsf"] > 0

    # 2) Supported corpus validation.
    assert validate_corpus(data_dir) == []

    # 3) Supported KG emit path.
    ear_ttl, _ = emit_ear(data_dir, kg_dir)
    nsf_ttl, _ = emit_nsf(data_dir, kg_dir)
    assert ear_ttl.exists()
    assert nsf_ttl.exists()

    # 4) Supported semantic assertions (SHACL + selected blocking checks).
    exit_code = validate_files(
        [str(ear_ttl), str(nsf_ttl)],
        Path("earCrawler/kg/shapes.ttl"),
        fail_on="supported",
        blocking_checks=("orphan_paragraphs", "entity_mentions_without_type"),
    )
    assert exit_code == 0

    # 5) Regression guard for NSF entity preservation in emitted KG.
    nsf_graph = Graph()
    nsf_graph.parse(nsf_ttl, format="ttl")
    for entity_name in (
        "John Smith",
        "University Of Testing",
        "R01-abc123",
        "National Science Foundation",
    ):
        assert (URIRef(str(_iri_for_entity(entity_name))), RDF.type, EAR_NS.Entity) in nsf_graph
