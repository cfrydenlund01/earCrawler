from __future__ import annotations

import json
from pathlib import Path

from earCrawler.kg.provenance_store import ProvenanceRecorder
from earCrawler.loaders.csl_loader import load_csl_by_query
from earCrawler.transforms import CanonicalRegistry


class DummyJena:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def update(self, query: str) -> None:
        self.queries.append(query)


def _search_stub(*args, **kwargs):
    return [
        {
            "id": "acme-1",
            "name": "ACME corp",
            "country": "u.s.",
            "programs": ["bis"],
            "source_url": "https://trade.gov/acme",
        }
    ]


def test_canonical_registry_applied_in_loader(tmp_path: Path) -> None:
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text(
        json.dumps(
            {
                "names": {"acme corp": "ACME Corporation"},
                "countries": {"u.s.": "United States"},
                "programs": {"bis": "BIS Entity List"},
            }
        ),
        encoding="utf-8",
    )

    registry = CanonicalRegistry(alias_path=alias_path)
    jena = DummyJena()
    recorder = ProvenanceRecorder(
        manifest_path=tmp_path / "prov.json",
        prov_dir=tmp_path / "prov",
    )

    load_csl_by_query(
        "acme",
        jena=jena,
        registry=registry,
        provenance=recorder,
        search_fn=_search_stub,
    )

    assert jena.queries, "expected at least one upsert"
    query = jena.queries[0]
    assert "ACME Corporation" in query
    assert "United States" in query
    assert "BIS Entity List" in query
