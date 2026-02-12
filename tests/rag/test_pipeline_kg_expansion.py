from __future__ import annotations

from earCrawler.kg.iri import section_iri
from earCrawler.rag import pipeline


class _FakeGateway:
    def select(self, query_id: str, params: dict[str, object]) -> list[dict[str, object]]:
        assert query_id == "kg_expand_by_section_id"
        source = str(params.get("section_iri") or "")
        s736 = section_iri("EAR-736.2(b)")
        s740 = section_iri("EAR-740.1")
        if source == s736:
            return [
                {
                    "source": s736,
                    "predicate": "https://ear.example.org/schema#mentions",
                    "target": s740,
                    "graph_iri": "https://ear.example.org/graph/kg/test",
                    "section_label": "General prohibitions",
                    "target_label": "License exceptions",
                }
            ]
        return []


def test_answer_with_rag_includes_structured_kg_paths(monkeypatch) -> None:
    monkeypatch.setenv("EARCRAWLER_ENABLE_KG_EXPANSION", "1")
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PROVIDER", "fuseki")
    monkeypatch.setattr(pipeline, "_create_fuseki_gateway", lambda: _FakeGateway())
    monkeypatch.setattr(
        pipeline,
        "retrieve_regulation_context",
        lambda *_a, **_k: [
            {
                "section_id": "EAR-736.2(b)",
                "text": "General prohibitions include license triggers.",
                "score": 1.0,
                "raw": {"id": "EAR-736.2(b)", "section": "EAR-736.2(b)"},
            }
        ],
    )

    result = pipeline.answer_with_rag(
        "What applies?",
        strict_retrieval=False,
        generate=False,
    )

    assert result["kg_expansions"]
    assert result["kg_paths_used"]
    assert result["kg_expansions"][0]["section_id"] == "EAR-736.2(b)"
    assert result["kg_paths_used"][0]["start_section_id"] == "EAR-736.2(b)"
    assert result["kg_paths_used"][0]["edges"][0]["predicate"].endswith("mentions")


def test_answer_with_rag_multihop_mode_toggle(monkeypatch) -> None:
    monkeypatch.setenv("EARCRAWLER_ENABLE_KG_EXPANSION", "1")
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PROVIDER", "fuseki")
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_MODE", "multihop_only")
    monkeypatch.setattr(pipeline, "_create_fuseki_gateway", lambda: _FakeGateway())
    monkeypatch.setattr(
        pipeline,
        "retrieve_regulation_context",
        lambda *_a, **_k: [
            {
                "section_id": "EAR-736.2(b)",
                "text": "General prohibitions include license triggers.",
                "score": 1.0,
                "raw": {"id": "EAR-736.2(b)", "section": "EAR-736.2(b)"},
            }
        ],
    )

    non_multihop = pipeline.answer_with_rag(
        "What applies?",
        task="entity_obligation",
        strict_retrieval=False,
        generate=False,
    )
    assert non_multihop["kg_expansions"] == []
    assert non_multihop["kg_paths_used"] == []

    multihop = pipeline.answer_with_rag(
        "What applies?",
        task="multihop",
        strict_retrieval=False,
        generate=False,
    )
    assert multihop["kg_expansions"]
    assert multihop["kg_paths_used"]
