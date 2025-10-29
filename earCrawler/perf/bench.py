from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import rdflib


@dataclass
class BenchResult:
    timings: Dict[str, float]

    def to_json(self) -> str:
        return json.dumps({"timings": self.timings}, indent=2)


def run_benchmarks(fixtures: Path, *, iterations: int = 1) -> BenchResult:
    timings: Dict[str, float] = {}
    ttl = fixtures / "kg" / "ear_small.ttl"
    if not ttl.exists():
        raise FileNotFoundError(f"Fixture not found: {ttl}")
    graph = rdflib.Graph()
    start = time.perf_counter()
    for _ in range(iterations):
        graph.parse(ttl, format="turtle")
    timings["load_ttl"] = (time.perf_counter() - start) / iterations

    q = """
PREFIX ear: <https://ear.example.org/schema#>
SELECT (COUNT(?s) AS ?cnt)
WHERE { ?s a ear:Entity }
"""
    start = time.perf_counter()
    for _ in range(iterations):
        list(graph.query(q))
    timings["count_entities"] = (time.perf_counter() - start) / iterations
    return BenchResult(timings=timings)
