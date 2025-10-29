from __future__ import annotations

import json
from pathlib import Path

from earCrawler.kg.anchors import AnchorIndex
from earCrawler.kg.provenance_store import ProvenanceRecorder
from earCrawler.loaders.ear_parts_loader import load_parts_from_fr


class DummyJena:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def update(self, query: str) -> None:
        self.queries.append(query)


def _search_stub(*args, **kwargs):
    return {
        "results": [
            {
                "document_number": "2024-12345",
                "title": "Export Administration Regulations Update",
                "abstract": "This rule amends 15 CFR Part 734 with new text impacting ACME Corp.",
                "excerpts": [
                    "Changes to 15 CFR Part 734 and 736 affecting ACME Corp",
                ],
                "html_url": "https://www.federalregister.gov/doc/2024-12345",
                "publication_date": "2024-02-01",
            }
        ]
    }


def test_fr_loader_records_anchors_and_delta(tmp_path: Path) -> None:
    manifest = tmp_path / "prov.json"
    prov_dir = tmp_path / "prov"
    anchors_path = tmp_path / "anchors.json"

    jena = DummyJena()
    recorder = ProvenanceRecorder(manifest_path=manifest, prov_dir=prov_dir)
    anchors = AnchorIndex(storage_path=anchors_path)
    parts = load_parts_from_fr(
        "Export Administration Regulations",
        jena=jena,
        provenance=recorder,
        anchor_index=anchors,
        search_fn=_search_stub,
        entity_names={"acme": "ACME Corp"},
    )
    assert "734" in parts
    assert len(jena.queries) >= 3
    assert anchors_path.exists()

    data = json.loads(anchors_path.read_text(encoding="utf-8"))
    assert "734" in data
    assert data["734"][0]["document_id"] == "2024-12345"
    mention_updates = [q for q in jena.queries if "mentionStrength" in q]
    assert mention_updates, "mention strength updates expected"

    # Second run should detect no deltas, yielding no SPARQL updates
    jena_second = DummyJena()
    recorder_second = ProvenanceRecorder(manifest_path=manifest, prov_dir=prov_dir)
    anchors_second = AnchorIndex(storage_path=anchors_path)
    load_parts_from_fr(
        "Export Administration Regulations",
        jena=jena_second,
        provenance=recorder_second,
        anchor_index=anchors_second,
        search_fn=_search_stub,
        entity_names={"acme": "ACME Corp"},
    )
    assert len(jena_second.queries) == 0
