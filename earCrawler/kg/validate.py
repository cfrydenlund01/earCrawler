from __future__ import annotations

"""Validation helpers for EAR knowledge graph Turtle files.

The functions here perform offline SPARQL sanity checks and SHACL shape
validation without any network access.  Keep API keys in Windows Credential
Manager or your vault; do not hard-code secrets in code.
"""

from pathlib import Path
from typing import Iterable

from rdflib import Graph
from pyshacl import validate as shacl_validate

from .queries import iter_queries


def run_sparql_checks(graph: Graph) -> list[tuple[str, int]]:
    """Run all SPARQL sanity checks over ``graph``.

    Returns a list of ``(check_name, violation_count)`` sorted by check name.
    """

    results: list[tuple[str, int]] = []
    for name, query in iter_queries():
        qres = graph.query(query)
        count = len(list(qres))
        results.append((name, count))
    return results


def run_shacl(
    graph: Graph, shapes_path: str | Path
) -> tuple[bool, Graph, str]:
    """Validate ``graph`` against ``shapes_path`` using ``pyshacl``."""

    conforms, results_graph, results_text = shacl_validate(
        graph,
        shacl_graph=Graph().parse(str(shapes_path), format="turtle"),
        advanced=True,
        inference="rdfs",
        abort_on_first=False,
    )
    return bool(conforms), results_graph, str(results_text)


def _load_graph(path: Path) -> Graph:
    """Parse ``path`` into a graph."""

    g = Graph()
    g.parse(path, format="turtle")
    return g


def validate_files(
    paths: Iterable[str],
    shapes_path: str | Path,
    *,
    fail_on: str = "any",
) -> int:
    """Validate one or more Turtle files.

    Parameters
    ----------
    paths:
        Iterable of file paths to Turtle documents.
    shapes_path:
        Path to a SHACL shapes graph.
    fail_on:
        One of ``"any"``, ``"shacl-only"``, ``"sparql-only"`` controlling the
        exit behaviour.

    Returns
    -------
    int
        ``0`` if clean, ``1`` if violations are found, ``2`` on usage errors.
    """

    files = sorted({str(Path(p)) for p in paths})
    if not files:
        print("No TTL files provided", flush=True)
        return 2

    shapes = Path(shapes_path)
    if not shapes.is_file():
        print(f"Shapes file not found: {shapes}", flush=True)
        return 2

    headers = ["file", "shacl"] + [name for name, _ in iter_queries()]
    rows: list[list[str]] = []
    any_sparql = False
    any_shacl = False

    for file in files:
        fp = Path(file)
        if not fp.is_file():
            print(f"File not found: {file}", flush=True)
            return 2
        g = _load_graph(fp)
        sparql_counts = run_sparql_checks(g)
        conforms, _, _ = run_shacl(g, shapes)
        row = [file, str(conforms)]
        for name, count in sparql_counts:
            row.append(str(count))
            if count:
                any_sparql = True
        if not conforms:
            any_shacl = True
        rows.append(row)

    # Deterministic table output
    col_widths = [
        max(len(h), *(len(r[i]) for r in rows))
        for i, h in enumerate(headers)
    ]
    header_line = " ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    )
    print(header_line)
    for r in rows:
        print(" ".join(r[i].ljust(col_widths[i]) for i in range(len(headers))))

    if fail_on == "any":
        return 1 if any_sparql or any_shacl else 0
    if fail_on == "shacl-only":
        return 1 if any_shacl else 0
    if fail_on == "sparql-only":
        return 1 if any_sparql else 0
    return 2


__all__ = ["run_sparql_checks", "run_shacl", "validate_files"]
