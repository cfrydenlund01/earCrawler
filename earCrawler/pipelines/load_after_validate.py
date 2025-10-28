from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from pyshacl import validate
from rdflib import Graph

from earCrawler.utils.io_paths import DIST, SCHEMA, SHAPES

FUSEKI = os.getenv("EAR_FUSEKI_DATASET", "http://localhost:3030/ear")
GRAPH = os.getenv("EAR_TARGET_GRAPH", "https://ear.example.org/graph/main")


def validate_file(ttl: Path) -> None:
    data_graph = Graph().parse(ttl.as_posix(), format="turtle")
    shapes_graph = Graph()
    for shape in SHAPES:
        shapes_graph.parse(shape.as_posix(), format="turtle")
    ontology_graph = Graph().parse(SCHEMA.as_posix(), format="turtle")
    conforms, _, report = validate(
        data_graph,
        shacl_graph=shapes_graph,
        ont_graph=ontology_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    if not conforms:
        print(report)
        raise SystemExit(2)


def load_file(ttl: Path) -> None:
    with open(ttl, "rb") as handle:
        response = requests.put(
            f"{FUSEKI}/data",
            params={"graph": GRAPH},
            data=handle,
            headers={"Content-Type": "text/turtle"},
            timeout=60,
        )
    response.raise_for_status()


def main(args: list[str]) -> int:
    target = Path(args[0]) if args else DIST / "bundle.ttl"
    if not target.exists():
        raise SystemExit(f"Missing {target}. Run build_ttl.py first.")
    validate_file(target)
    if os.getenv("EAR_ENABLE_LOAD", "0") == "1":
        load_file(target)
        print(f"Loaded: {target}")
    else:
        print("Validation passed. Skipping load (EAR_ENABLE_LOAD!=1).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
