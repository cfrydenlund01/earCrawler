from __future__ import annotations

import json
from pathlib import Path

from earCrawler.kg.provenance_store import ProvenanceRecorder
from earCrawler.loaders.csl_loader import load_csl_by_query


class DummyJena:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def update(self, query: str) -> None:
        self.queries.append(query)


def _search_stub(*args, **kwargs):
    return [
        {
            "id": "acme-1",
            "name": "ACME Corp",
            "country": "U.S.",
            "programs": ["BIS"],
            "source_url": "https://trade.gov/acme",
        }
    ]


def test_csl_loader_delta_skips_redundant_updates(tmp_path: Path) -> None:
    manifest = tmp_path / "prov.json"
    prov_dir = tmp_path / "prov"

    jena = DummyJena()
    recorder = ProvenanceRecorder(manifest_path=manifest, prov_dir=prov_dir)
    load_csl_by_query(
        "acme",
        jena=jena,
        provenance=recorder,
        search_fn=_search_stub,
    )
    assert len(jena.queries) == 1
    assert manifest.exists()

    jena.queries.clear()
    recorder_second = ProvenanceRecorder(manifest_path=manifest, prov_dir=prov_dir)
    load_csl_by_query(
        "acme",
        jena=jena,
        provenance=recorder_second,
        search_fn=_search_stub,
    )
    assert len(jena.queries) == 0

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert "https://ear.example.org/entity/acme_1" in manifest_payload
