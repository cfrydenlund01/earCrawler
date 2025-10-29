from pathlib import Path

import rdflib

from earCrawler.kg.integrity import run_checks


def test_integrity_detects_missing_name(tmp_path: Path) -> None:
    ttl = tmp_path / "graph.ttl"
    ttl.write_text(
        """
@prefix ear: <https://ear.example.org/schema#> .
@prefix ent: <https://ear.example.org/entity/> .

ent:foo a ear:Entity .
ear:part734 a ear:Part .
""",
        encoding="utf-8",
    )
    graph = rdflib.Graph()
    graph.parse(ttl, format="turtle")
    issues = {issue.name: issue.count for issue in run_checks(graph)}
    assert issues["missing_entity_names"] == 1
