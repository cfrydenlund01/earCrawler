from __future__ import annotations

from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

from earCrawler.transforms.csl_to_rdf import to_bindings
from earCrawler.transforms.ear_fr_to_rdf import pick_parts
from earCrawler.utils.io_paths import DIST, ensure_dirs

EAR = Namespace("https://ear.example.org/schema#")
ENT = Namespace("https://ear.example.org/entity/")
PART = Namespace("https://ear.example.org/part/")


def entity_triples(graph: Graph, binding: dict) -> None:
    entity_ref = ENT[binding["id"].replace(" ", "_")]
    graph.add((entity_ref, RDF.type, EAR.Entity))
    graph.add((entity_ref, EAR.name, Literal(binding["name"])))
    graph.add((entity_ref, EAR.source, Literal(binding["source"])))
    if binding.get("country"):
        graph.add((entity_ref, EAR.country, Literal(binding["country"])))
    if binding.get("programs"):
        graph.add((entity_ref, EAR.programs, Literal(binding["programs"])))


def part_triples(graph: Graph, parts: list[str]) -> None:
    for notation in pick_parts(parts):
        node = PART[notation]
        graph.add((node, RDF.type, EAR.Part))
        graph.add((node, EAR.notation, Literal(notation)))
        graph.add((node, EAR.title, Literal(f"15 CFR Part {notation}")))


def build_samples() -> Path:
    ensure_dirs()
    graph = Graph()
    binding = to_bindings(
        {
            "name": "SAMPLE CO",
            "country": "CN",
            "source": "CSL",
            "programs": ["Entity List"],
            "id": "sample",
        }
    )
    entity_triples(graph, binding)
    part_triples(graph, ["744", "736"])
    output = DIST / "bundle.ttl"
    graph.serialize(output.as_posix(), format="turtle")
    return output


if __name__ == "__main__":
    print(build_samples())
