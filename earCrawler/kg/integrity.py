from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

import rdflib

EAR_NS = rdflib.Namespace("https://ear.example.org/schema#")

@dataclass
class IntegrityIssue:
    name: str
    count: int
    query: str


QUERIES: Dict[str, str] = {
    "missing_entity_names": """
PREFIX ear: <https://ear.example.org/schema#>
SELECT (COUNT(?s) AS ?count)
WHERE {
  ?s a ear:Entity .
  FILTER NOT EXISTS { ?s ear:name ?name }
}
""",
    "parts_without_mentions": """
PREFIX ear: <https://ear.example.org/schema#>
SELECT (COUNT(?part) AS ?count)
WHERE {
  ?part a ear:Part .
  FILTER NOT EXISTS { ?mention ear:mentionsPart ?part }
}
""",
    "policy_hints_without_priority": """
PREFIX ear: <https://ear.example.org/schema#>
SELECT (COUNT(?hint) AS ?count)
WHERE {
  ?hint a ear:PolicyHint .
  FILTER NOT EXISTS { ?hint ear:hintPriority ?priority }
}
""",
}


def run_checks(graph: rdflib.Graph, queries: Dict[str, str] | None = None) -> List[IntegrityIssue]:
    checks = []
    for name, query in (queries or QUERIES).items():
        result = graph.query(query)
        count = 0
        for row in result:
            if row and len(row) > 0:
                try:
                    count = int(row[0])
                except Exception:
                    count = 0
        checks.append(IntegrityIssue(name=name, count=count, query=query))
    return checks


def check_file(ttl_path: Path) -> List[IntegrityIssue]:
    graph = rdflib.Graph()
    graph.parse(ttl_path, format="turtle")
    return run_checks(graph)
