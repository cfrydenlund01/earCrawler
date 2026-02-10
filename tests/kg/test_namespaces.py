from __future__ import annotations

from pathlib import Path

from earCrawler.kg.emit_ear import emit_ear
from earCrawler.kg.emit_nsf import emit_nsf
from earCrawler.kg.iri import canonicalize_iri, paragraph_iri, section_iri
from earCrawler.kg.namespaces import ENTITY_NS, LEGACY_NS_LIST, RESOURCE_NS, SCHEMA_NS


def test_namespace_constants_are_canonical() -> None:
    assert SCHEMA_NS == "https://ear.example.org/schema#"
    assert RESOURCE_NS == "https://ear.example.org/resource/"
    assert ENTITY_NS == "https://ear.example.org/entity/"


def test_iri_builders_use_canonical_bases() -> None:
    assert section_iri("EAR-736.2(b)").startswith(RESOURCE_NS)
    assert paragraph_iri("a" * 64).startswith(RESOURCE_NS)


def test_legacy_iris_canonicalize_deterministically() -> None:
    assert canonicalize_iri("https://example.org/ear#s_738_1") == section_iri("738.1")
    assert canonicalize_iri("https://example.org/ear#p_aaaaaaaaaaaaaaaa") == paragraph_iri(
        "a" * 64
    )
    assert canonicalize_iri("https://example.org/ear#exception/740_1") == (
        "https://ear.example.org/resource/ear/exception/740_1"
    )
    assert canonicalize_iri("https://example.org/entity#Entity") == (
        "https://ear.example.org/schema#Entity"
    )


def test_emitters_do_not_emit_legacy_namespaces(tmp_path: Path) -> None:
    fixtures = Path("tests/kg/fixtures")
    out_dir = tmp_path / "kg"

    ear_ttl, _ = emit_ear(fixtures, out_dir)
    nsf_ttl, _ = emit_nsf(fixtures, out_dir)

    for path in (ear_ttl, nsf_ttl):
        text = path.read_text(encoding="utf-8")
        assert "ear.example.org" in text
        for legacy in LEGACY_NS_LIST:
            assert legacy not in text

