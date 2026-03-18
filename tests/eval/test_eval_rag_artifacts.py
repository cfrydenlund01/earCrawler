from __future__ import annotations

from scripts.eval.eval_rag_artifacts import (
    sanitize_citations,
    sanitize_kg_expansions,
    sanitize_kg_paths,
    sanitize_retrieved_docs,
)


def test_sanitize_citations_keeps_supported_fields_only():
    citations = [
        {"section_id": "EAR-740.1", "quote": "q", "span_id": "s", "source": "retrieval", "extra": "drop"},
        "invalid",
    ]

    result = sanitize_citations(citations)

    assert result == [
        {
            "section_id": "EAR-740.1",
            "quote": "q",
            "span_id": "s",
            "source": "retrieval",
        }
    ]


def test_sanitize_retrieved_docs_normalizes_sections():
    docs = [
        {"id": "doc-1", "section": "740.1", "url": "u", "title": "t", "score": 0.8, "source": "retrieval"},
    ]

    result = sanitize_retrieved_docs(docs)

    assert result == [
        {
            "id": "doc-1",
            "section": "EAR-740.1",
            "url": "u",
            "title": "t",
            "score": 0.8,
            "source": "retrieval",
        }
    ]


def test_sanitize_kg_paths_filters_invalid_edges_and_sorts():
    paths = [
        {
            "path_id": "b",
            "start_section_id": "740.2",
            "graph_iri": "g",
            "confidence": 0.3,
            "edges": [
                {"source": "s", "predicate": "", "target": "t"},
                {"source": "s", "predicate": "p", "target": "t"},
            ],
        },
        {
            "path_id": "a",
            "start_section_id": "740.1",
            "edges": [{"source": "x", "predicate": "y", "target": "z"}],
        },
    ]

    result = sanitize_kg_paths(paths)

    assert [row["path_id"] for row in result] == ["a", "b"]
    assert result[0]["start_section_id"] == "EAR-740.1"
    assert result[1]["start_section_id"] == "EAR-740.2"
    assert result[1]["edges"] == [{"source": "s", "predicate": "p", "target": "t"}]


def test_sanitize_kg_expansions_normalizes_sections_and_nested_paths():
    expansions = [
        {
            "section_id": "740.2",
            "text": "   text  ",
            "source": "kg",
            "related_sections": ["740.1", "invalid"],
            "paths": [{"path_id": "p", "start_section_id": "740.2", "edges": [{"source": "a", "predicate": "b", "target": "c"}]}],
        },
        {"section_id": "not_a_section", "paths": []},
    ]

    result = sanitize_kg_expansions(expansions)

    assert len(result) == 2
    row = next(item for item in result if item["section_id"] == "EAR-740.2")
    assert row["section_id"] == "EAR-740.2"
    assert row["text"] == "text"
    assert row["source"] == "kg"
    assert row["related_sections"] == ["EAR-740.1", "invalid"]
    assert row["paths"][0]["start_section_id"] == "EAR-740.2"
    assert any(item["section_id"] == "not_a_section" for item in result)
