from __future__ import annotations

"""One-time namespace migration utility (deterministic + idempotent).

Supported inputs:
- RDF: .ttl/.nt/.nq (IRIs are canonicalized via earCrawler.kg.iri.canonicalize_iri)
- SPARQL: .sparql/.rq (optional raw prefix replacements)
- JSON/JSONL: only known reference fields are rewritten (IRIs canonicalized)

This script is intentionally conservative: for JSON/JSONL it will not rewrite
arbitrary free-text fields.
"""

import argparse
import glob
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import rdflib
from rdflib import ConjunctiveGraph, Graph, URIRef

from earCrawler.kg.iri import canonicalize_iri
from earCrawler.kg.namespaces import ENTITY_NS, RESOURCE_NS, SCHEMA_NS


_RDF_EXTS = {".ttl", ".nt", ".nq"}
_SPARQL_EXTS = {".sparql", ".rq"}
_JSON_EXTS = {".json", ".jsonl"}


def _iter_globbed_paths(patterns: Iterable[str]) -> Iterator[Path]:
    seen: set[Path] = set()
    for pat in patterns:
        for raw in glob.glob(pat, recursive=True):
            path = Path(raw)
            if path.is_file():
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield resolved


def _rewrite_text_with_maps(text: str, maps: list[tuple[str, str]]) -> str:
    out = text
    # Deterministic application: longest "from" first to avoid partial overlaps.
    for src, dst in sorted(maps, key=lambda p: (-len(p[0]), p[0], p[1])):
        if src and src != dst:
            out = out.replace(src, dst)
    return out


def _rewrite_known_json_fields(obj: Any) -> tuple[Any, int]:
    """Return (rewritten_obj, rewrite_count)."""

    count = 0
    target_list_keys = {"kg_nodes", "kg_paths", "kg_entities", "label_hints"}

    def _canon(value: Any) -> Any:
        nonlocal count
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            new = canonicalize_iri(value)
            if new != value:
                count += 1
            return new
        return value

    def _rewrite(value: Any) -> Any:
        if isinstance(value, dict):
            for key, inner in list(value.items()):
                if key in target_list_keys and isinstance(inner, list):
                    value[key] = [_canon(v) for v in inner]
                else:
                    value[key] = _rewrite(inner)
            return value
        if isinstance(value, list):
            return [_rewrite(v) for v in value]
        return value

    if isinstance(obj, (dict, list)):
        return _rewrite(obj), count
    return obj, count


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def _dump_jsonl(path: Path, items: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def _rewrite_rdf_file(in_path: Path, out_path: Path) -> int:
    """Rewrite IRIs in an RDF file; returns rewritten-IRI count (approx)."""

    ext = in_path.suffix.lower()
    fmt = {"ttl": "turtle", "nt": "nt", "nq": "nquads"}.get(ext.lstrip("."))
    if not fmt:
        raise ValueError(f"Unsupported RDF extension: {in_path}")

    if fmt == "nquads":
        graph: Graph | ConjunctiveGraph = ConjunctiveGraph()
    else:
        graph = Graph()
    graph.parse(in_path, format=fmt)

    rewritten = 0

    def _canon_term(term: Any) -> Any:
        nonlocal rewritten
        if isinstance(term, URIRef):
            new = canonicalize_iri(str(term))
            if new != str(term):
                rewritten += 1
            return URIRef(new)
        return term

    if isinstance(graph, ConjunctiveGraph):
        out = ConjunctiveGraph()
        for ctx in graph.contexts():
            ctx_id = ctx.identifier
            new_ctx_id = _canon_term(ctx_id)
            out_ctx = out.get_context(new_ctx_id)
            for s, p, o in ctx.triples((None, None, None)):
                out_ctx.add((_canon_term(s), _canon_term(p), _canon_term(o)))
        _write_sorted_nquads(out, out_path)
        return rewritten

    out_g = Graph()
    for prefix, ns in graph.namespace_manager.namespaces():
        ns_str = str(ns)
        if ns_str == "https://example.org/ear#":
            out_g.bind(prefix, SCHEMA_NS, replace=True)
        elif ns_str == "https://example.org/entity#":
            out_g.bind(prefix, ENTITY_NS, replace=True)
        elif ns_str == "http://example.org/ear/":
            out_g.bind(prefix, f"{RESOURCE_NS}legacy/ear/", replace=True)
        else:
            out_g.bind(prefix, ns, replace=True)
    for s, p, o in graph.triples((None, None, None)):
        out_g.add((_canon_term(s), _canon_term(p), _canon_term(o)))
    _write_sorted_turtle(out_g, out_path)
    return rewritten


def _write_sorted_turtle(graph: Graph, out_path: Path) -> None:
    prefixes = sorted(graph.namespace_manager.namespaces(), key=lambda x: x[0])
    nm = graph.namespace_manager
    lines: list[str] = []
    for s, p, o in graph:
        lines.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} .")
    lines.sort()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for prefix, ns in prefixes:
            handle.write(f"@prefix {prefix}: <{ns}> .\n")
        handle.write("\n")
        for line in lines:
            handle.write(line + "\n")


def _write_sorted_nquads(graph: ConjunctiveGraph, out_path: Path) -> None:
    nm = graph.namespace_manager
    lines: list[str] = []
    for ctx in graph.contexts():
        ctx_n3 = ctx.identifier.n3(nm)
        for s, p, o in ctx.triples((None, None, None)):
            lines.append(f"{s.n3(nm)} {p.n3(nm)} {o.n3(nm)} {ctx_n3} .")
    lines.sort()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class RewriteResult:
    path: Path
    rewrites: int
    kind: str


def migrate(
    patterns: list[str],
    *,
    out_dir: Path | None,
    in_place: bool,
    text_maps: list[tuple[str, str]],
) -> list[RewriteResult]:
    results: list[RewriteResult] = []
    for in_path in _iter_globbed_paths(patterns):
        ext = in_path.suffix.lower()
        if ext in _RDF_EXTS:
            out_path = in_path if in_place else _mirror_path(in_path, out_dir)
            rewrites = _rewrite_rdf_file(in_path, out_path)
            results.append(RewriteResult(path=out_path, rewrites=rewrites, kind="rdf"))
            continue
        if ext in _SPARQL_EXTS:
            text = in_path.read_text(encoding="utf-8")
            out_text = _rewrite_text_with_maps(text, text_maps)
            out_path = in_path if in_place else _mirror_path(in_path, out_dir)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(out_text, encoding="utf-8")
            rewrites = 1 if out_text != text else 0
            results.append(RewriteResult(path=out_path, rewrites=rewrites, kind="sparql"))
            continue
        if ext in _JSON_EXTS:
            out_path = in_path if in_place else _mirror_path(in_path, out_dir)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if ext == ".jsonl":
                items = list(_iter_jsonl(in_path))
                rewrites = 0
                for item in items:
                    _, c = _rewrite_known_json_fields(item)
                    rewrites += c
                _dump_jsonl(out_path, items)
                results.append(RewriteResult(path=out_path, rewrites=rewrites, kind="jsonl"))
            else:
                obj = _load_json(in_path)
                _, rewrites = _rewrite_known_json_fields(obj)
                _dump_json(out_path, obj)
                results.append(RewriteResult(path=out_path, rewrites=rewrites, kind="json"))
            continue
    return results


def _mirror_path(in_path: Path, out_dir: Path | None) -> Path:
    if out_dir is None:
        raise ValueError("--out-dir is required unless --in-place is set")
    out_dir = out_dir.resolve()
    cwd = Path(os.getcwd()).resolve()
    try:
        rel = in_path.resolve().relative_to(cwd)
    except Exception:
        # If the path is outside CWD, fall back to writing under out_dir using the basename.
        rel = Path(in_path.name)
    return out_dir / rel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate KG namespace references.")
    parser.add_argument(
        "patterns",
        nargs="+",
        help="File glob patterns (supports ** with --recursive globs).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output root directory (recommended).",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite files in place (use with care).",
    )
    parser.add_argument(
        "--from",
        dest="from_list",
        action="append",
        default=[],
        help="Optional raw-text rewrite source (repeatable; pair with --to).",
    )
    parser.add_argument(
        "--to",
        dest="to_list",
        action="append",
        default=[],
        help="Optional raw-text rewrite destination (repeatable; pair with --from).",
    )
    args = parser.parse_args(argv)

    if args.in_place and args.out_dir is not None:
        raise SystemExit("Provide either --in-place or --out-dir, not both.")
    if not args.in_place and args.out_dir is None:
        raise SystemExit("Provide --out-dir (recommended) or set --in-place.")
    if len(args.from_list) != len(args.to_list):
        raise SystemExit("--from and --to must be provided the same number of times.")

    maps = list(zip(args.from_list, args.to_list))
    results = migrate(
        list(args.patterns),
        out_dir=args.out_dir,
        in_place=bool(args.in_place),
        text_maps=maps,
    )

    changed = [r for r in results if r.rewrites]
    print(f"Processed {len(results)} file(s); changed {len(changed)} file(s).")
    by_kind: dict[str, int] = {}
    for r in changed:
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
    if by_kind:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items()))
        print(f"Changed by kind: {summary}")
    for r in changed:
        print(f"- {r.kind}: {r.path} (rewrites={r.rewrites})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
