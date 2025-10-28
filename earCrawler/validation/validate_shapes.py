from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph

from earCrawler.utils.io_paths import DIST
from pyshacl import validate

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "ear.ttl"
SHAPES = [ROOT / "shapes" / "entities.shacl.ttl", ROOT / "shapes" / "parts.shacl.ttl"]


def run_validation(data_files: list[Path]) -> int:
    data_graph = Graph()
    for file_path in data_files:
        data_graph.parse(file_path.resolve().as_uri(), format="turtle")
    sh_graph = Graph()
    for shape in SHAPES:
        sh_graph.parse(shape.resolve().as_uri(), format="turtle")
    ont_graph = Graph()
    ont_graph.parse(SCHEMA.resolve().as_uri(), format="turtle")

    conforms, report_graph, report_text = validate(
        data_graph,
        shacl_graph=sh_graph,
        ont_graph=ont_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    print(report_text)
    return 0 if conforms else 2


if __name__ == "__main__":
    if len(sys.argv) > 1:
        targets = [Path(arg) for arg in sys.argv[1:]]
    else:
        targets = [
            ROOT / "samples" / "sample_entities.ttl",
            ROOT / "samples" / "sample_parts.ttl",
        ]
        bundle = DIST / "bundle.ttl"
        if bundle.exists():
            targets.append(bundle)
    sys.exit(run_validation(targets))
