from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Set, Tuple

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL
from rdflib.query import Result

from earCrawler.utils.io_paths import ROOT

EX = Namespace("http://example.com/reasoner-smoke#")

KG_DIR = ROOT / "kg"
REPORTS_DIR = KG_DIR / "reports"
QUERIES = {
    "rdfs": [
        ("subclass", KG_DIR / "queries" / "infer_subclass_ask.rq", "Subclass inference via rdfs:subClassOf"),
        ("domain-range", KG_DIR / "queries" / "infer_domain_range_ask.rq", "Domain and range infer types"),
        ("equivalence", KG_DIR / "queries" / "infer_equivalence_ask.rq", "Equivalent classes propagate type"),
    ],
    "owlmini": [
        ("subclass", KG_DIR / "queries" / "infer_subclass_ask.rq", "Subclass inference via rdfs:subClassOf"),
        ("domain-range", KG_DIR / "queries" / "infer_domain_range_ask.rq", "Domain and range infer types"),
        ("equivalence", KG_DIR / "queries" / "infer_equivalence_ask.rq", "Equivalent classes propagate type"),
    ],
}
SELECT_QUERY = KG_DIR / "queries" / "infer_report_select.rq"
DATA_FILES = [
    KG_DIR / "testdata" / "reasoner_smoke.ttl",
]


def _load_graph(files: Iterable[Path]) -> Graph:
    graph = Graph()
    for file_path in files:
        graph.parse(file_path.as_posix(), format="turtle")
    return graph


def _closure_subclass(graph: Graph) -> None:
    added = True
    while added:
        added = False
        current_types = list(graph.triples((None, RDF.type, None)))
        for subj, _, obj in current_types:
            for _, _, super_class in graph.triples((obj, RDFS.subClassOf, None)):
                if (subj, RDF.type, super_class) not in graph:
                    graph.add((subj, RDF.type, super_class))
                    added = True


def _closure_domain_range(graph: Graph) -> None:
    added = True
    while added:
        added = False
        for prop, _, domain in graph.triples((None, RDFS.domain, None)):
            for subj, _, _ in graph.triples((None, prop, None)):
                if (subj, RDF.type, domain) not in graph:
                    graph.add((subj, RDF.type, domain))
                    added = True
        for prop, _, range_class in graph.triples((None, RDFS.range, None)):
            for _, _, obj in graph.triples((None, prop, None)):
                if (obj, RDF.type, range_class) not in graph:
                    graph.add((obj, RDF.type, range_class))
                    added = True


def _closure_equivalence(graph: Graph) -> None:
    parent: dict = {}

    def find(node):
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, _, b in graph.triples((None, OWL.equivalentClass, None)):
        union(a, b)
        union(b, a)

    if not parent:
        return

    equivalence_groups: dict = {}
    for node in parent.keys():
        root = find(node)
        equivalence_groups.setdefault(root, set()).add(node)

    current_types = list(graph.triples((None, RDF.type, None)))
    for subj, _, obj in current_types:
        root = find(obj) if obj in parent else obj
        equivalents = equivalence_groups.get(root, {obj})
        for cls in equivalents:
            if (subj, RDF.type, cls) not in graph:
                graph.add((subj, RDF.type, cls))


def run_inference(mode: str) -> Graph:
    graph = _load_graph(DATA_FILES)
    _closure_subclass(graph)
    _closure_domain_range(graph)
    _closure_equivalence(graph)
    return graph


def _read_query(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_ask(graph: Graph, query: str) -> bool:
    result = graph.query(query)
    if isinstance(result, bool):
        return result
    for row in result:
        if hasattr(row, "askAnswer"):
            return bool(row.askAnswer)
    return bool(result)


def _run_select(graph: Graph, query: str) -> Result:
    return graph.query(query)


def execute(mode: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    graph = run_inference(mode)
    ask_results: list[dict] = []
    summaries: list[str] = []

    for name, path, details in QUERIES[mode]:
        query_text = _read_query(path)
        passed = _run_ask(graph, query_text)
        ask_results.append({"name": name, "passed": passed, "details": details})
        summaries.append(f"{name}: {passed}")

    result = _run_select(graph, _read_query(SELECT_QUERY))
    json_path = REPORTS_DIR / f"inference-{mode}.json"
    txt_path = REPORTS_DIR / f"inference-{mode}.txt"
    select_path = REPORTS_DIR / f"inference-{mode}-select.srj"
    json_path.write_text(json.dumps(ask_results, indent=2), encoding="utf-8")
    txt_path.write_text("\n".join(summaries), encoding="utf-8")
    select_path.write_bytes(result.serialize(format="json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline inference smoke checks without Fuseki.")
    parser.add_argument("--mode", choices=("rdfs", "owlmini"), default="rdfs")
    args = parser.parse_args()
    execute(args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
