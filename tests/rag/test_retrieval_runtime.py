from __future__ import annotations

from earCrawler.kg.paths import KGExpansionSnippet, KGPath, KGPathEdge
from earCrawler.rag import retrieval_runtime



def test_build_retrieval_context_bundle_keeps_retrieval_and_kg_separate() -> None:
    bundle = retrieval_runtime.build_retrieval_context_bundle(
        [
            {
                "section_id": "EAR-740.1",
                "text": "License Exceptions intro.",
                "score": 0.9,
                "raw": {"id": "EAR-740.1", "section": "EAR-740.1"},
            }
        ],
        kg_expansion=[
            KGExpansionSnippet(
                section_id="EAR-740.1",
                text="KG expansion note.",
                source="kg-test",
                related_sections=["EAR-740.2"],
                paths=[
                    KGPath(
                        path_id="path:1",
                        start_section_id="EAR-740.1",
                        edges=[
                            KGPathEdge(
                                source="urn:sec:740.1",
                                predicate="urn:mentions",
                                target="urn:sec:740.2",
                            )
                        ],
                        graph_iri="urn:graph:test",
                        confidence=0.8,
                    )
                ],
            )
        ],
    )

    assert bundle.section_ids == ["EAR-740.1"]
    assert bundle.contexts == [
        "[EAR-740.1] License Exceptions intro.",
        "[EAR-740.1] KG expansion note.",
    ]
    assert bundle.retrieved_docs[0]["source"] == "retrieval"
    assert bundle.retrieved_docs[1]["source"] == "kg"
    assert bundle.kg_expansions_payload[0]["section_id"] == "EAR-740.1"
    assert bundle.kg_paths_payload[0]["path_id"] == "path:1"
