from __future__ import annotations

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
                "document_number": "2024-555",
                "title": "EAR Part 734 Guidance",
                "abstract": "Updates concerning 15 CFR Part 734 and screenings.",
                "excerpts": ["Part 734 retains BIS Entity List alignment."],
                "html_url": "https://www.federalregister.gov/doc/2024-555",
                "publication_date": "2024-01-10",
            }
        ]
    }


def test_policy_hints_apply_once(tmp_path: Path) -> None:
    hints_file = tmp_path / "hints.yml"
    hints_file.write_text(
        """
hints:
  - part: "734"
    program: "BIS Entity List"
    priority: 0.9
    rationale: "Test mapping"
""",
        encoding="utf-8",
    )

    manifest = tmp_path / "prov.json"
    prov_dir = tmp_path / "prov"
    anchors_path = tmp_path / "anchors.json"

    jena = DummyJena()
    recorder = ProvenanceRecorder(manifest_path=manifest, prov_dir=prov_dir)
    anchors = AnchorIndex(storage_path=anchors_path)

    load_parts_from_fr(
        "EAR",
        jena=jena,
        provenance=recorder,
        anchor_index=anchors,
        search_fn=_search_stub,
        policy_path=hints_file,
    )

    hint_queries = [q for q in jena.queries if "hasPolicyHint" in q]
    assert hint_queries, "expected policy hint insert"

    # second run should not reapply if unchanged
    jena_second = DummyJena()
    recorder_second = ProvenanceRecorder(manifest_path=manifest, prov_dir=prov_dir)
    anchors_second = AnchorIndex(storage_path=anchors_path)
    load_parts_from_fr(
        "EAR",
        jena=jena_second,
        provenance=recorder_second,
        anchor_index=anchors_second,
        search_fn=_search_stub,
        policy_path=hints_file,
    )
    hint_queries_second = [q for q in jena_second.queries if "hasPolicyHint" in q]
    assert not hint_queries_second
