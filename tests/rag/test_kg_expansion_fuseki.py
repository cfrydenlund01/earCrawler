from __future__ import annotations

from earCrawler.kg.iri import section_iri
from earCrawler.rag.kg_expansion_fuseki import expand_sections_via_fuseki


class _FakeGateway:
    def __init__(self, rows_by_source: dict[str, list[dict[str, object]]]) -> None:
        self.rows_by_source = rows_by_source
        self.calls: list[tuple[str, dict[str, object]]] = []

    def select(self, query_id: str, params: dict[str, object]) -> list[dict[str, object]]:
        self.calls.append((query_id, dict(params)))
        source = str(params.get("section_iri") or "")
        return list(self.rows_by_source.get(source, []))


def _rows_fixture() -> dict[str, list[dict[str, object]]]:
    s736 = section_iri("EAR-736.2(b)")
    s740 = section_iri("EAR-740.1")
    s744 = section_iri("EAR-744.6(b)(3)")
    node_a = "https://ear.example.org/resource/ear/policy/node-a"

    return {
        s736: [
            {
                "source": s736,
                "predicate": "https://ear.example.org/schema#relB",
                "target": s740,
                "graph_iri": "https://ear.example.org/graph/kg/test",
                "section_label": "Section 736.2(b)",
                "target_label": "License Exceptions",
            },
            {
                "source": s736,
                "predicate": "https://ear.example.org/schema#relA",
                "target": node_a,
                "graph_iri": "https://ear.example.org/graph/kg/test",
                "section_comment": "General prohibitions",
            },
        ],
        node_a: [
            {
                "source": node_a,
                "predicate": "https://ear.example.org/schema#relC",
                "target": s744,
                "graph_iri": "https://ear.example.org/graph/kg/test",
                "target_comment": "U.S. person support restriction",
            }
        ],
        s740: [],
        s744: [],
    }


def test_expand_sections_via_fuseki_deterministic_and_canonical() -> None:
    gateway = _FakeGateway(_rows_fixture())

    first = expand_sections_via_fuseki(
        ["736.2(b)"],
        gateway,
        max_paths_per_section=3,
        max_hops=2,
    )
    second = expand_sections_via_fuseki(
        ["EAR-736.2(b)"],
        gateway,
        max_paths_per_section=3,
        max_hops=2,
    )

    assert len(first) == 1
    assert len(second) == 1

    snippet = first[0]
    assert snippet.section_id == "EAR-736.2(b)"
    assert [p.path_id for p in first[0].paths] == [p.path_id for p in second[0].paths]
    assert snippet.paths[0].edges[0].predicate.endswith("relA")
    assert snippet.related_sections == ["EAR-740.1", "EAR-744.6(b)(3)"]
    assert snippet.text == "General prohibitions | License Exceptions"
    assert any(call[0] == "kg_expand_by_section_id" for call in gateway.calls)


def test_expand_sections_via_fuseki_enforces_hop_and_path_limits() -> None:
    gateway = _FakeGateway(_rows_fixture())

    expansions = expand_sections_via_fuseki(
        ["EAR-736.2(b)"],
        gateway,
        max_paths_per_section=1,
        max_hops=1,
    )

    assert len(expansions) == 1
    snippet = expansions[0]
    assert len(snippet.paths) == 1
    assert len(snippet.paths[0].edges) == 1
    assert snippet.paths[0].edges[0].predicate.endswith("relA")
