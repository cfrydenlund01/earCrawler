from __future__ import annotations

"""KG CLI commands and registrar."""

from importlib import resources
import json
from pathlib import Path
from typing import Any

import click

from earCrawler.kg import emit_ear, emit_nsf, fuseki
from earCrawler.kg.sparql import SPARQLClient
from earCrawler.kg.validate import validate_files
from earCrawler.security import policy


def _resolve_sparql_client() -> type[SPARQLClient]:
    """Support legacy tests that monkeypatch SPARQLClient on cli.__main__."""

    try:
        from earCrawler.cli import __main__ as main_mod

        patched = getattr(main_mod, "SPARQLClient", None)
        if patched is not None:
            return patched
    except Exception:
        pass
    return SPARQLClient


def _validate_ttls(
    ctx: click.Context,
    ttls: tuple[Path, ...],
    glob_pattern: str | None,
    shapes: Path | None,
    fail_on: str,
    blocking_checks: tuple[str, ...],
) -> None:
    paths: list[str] = []
    if glob_pattern:
        if ctx.args:
            paths.extend([glob_pattern, *ctx.args])
        else:
            pattern_path = Path(glob_pattern)
            paths.extend(str(p) for p in pattern_path.parent.glob(pattern_path.name))
    paths.extend(str(p) for p in ttls)

    if shapes is None:
        with resources.as_file(
            resources.files("earCrawler.kg").joinpath("shapes.ttl")
        ) as default_shapes:
            exit_code = validate_files(
                paths,
                default_shapes,
                fail_on=fail_on,
                blocking_checks=blocking_checks or None,
            )
    else:
        exit_code = validate_files(
            paths,
            shapes,
            fail_on=fail_on,
            blocking_checks=blocking_checks or None,
        )
    raise SystemExit(exit_code)


@click.group(name="kg")
def kg_group() -> None:
    """Knowledge graph utilities."""


@click.command(name="kg-export")
@click.option("--data-dir", default="data", help="Crawl JSONL directory.")
@click.option("--out-ttl", default="kg/ear_triples.ttl", help="Output TTL file.")
def kg_export(data_dir: str, out_ttl: str) -> None:
    """Export paragraphs & entities to Turtle for Jena TDB2."""

    from earCrawler.kg.triples import export_triples

    export_triples(Path(data_dir), Path(out_ttl))
    click.echo(f"Written triples to {out_ttl}")


@click.command(name="kg-load")
@policy.require_role("operator", "maintainer")
@policy.enforce
@click.option("--ttl", "-t", default="kg/ear_triples.ttl", help="Turtle file to load.")
@click.option("--db", "-d", default="db", help="TDB2 DB directory.")
@click.option(
    "--no-auto-install",
    is_flag=True,
    default=False,
    help="Disable auto-download of Apache Jena; fail if not present.",
)
def kg_load(ttl: str, db: str, no_auto_install: bool) -> None:
    """Load Turtle into a local TDB2 store."""

    from earCrawler.kg.loader import load_tdb

    load_tdb(Path(ttl), Path(db), auto_install=not no_auto_install)
    click.echo(f"Loaded {ttl} into TDB2 at {db}")


@click.command(name="kg-serve")
@policy.require_role("operator", "maintainer")
@policy.enforce
@click.option("--db", "-d", default="db", help="Path to TDB2 database directory.")
@click.option(
    "--dataset",
    default="/ear",
    show_default=True,
    help="Dataset name (must start with '/').",
)
@click.option(
    "--port", "-p", default=3030, show_default=True, type=int, help="Fuseki port."
)
@click.option(
    "--java-opts", default=None, help="Extra JVM opts (e.g., '-Xms1g -Xmx2g')."
)
@click.option(
    "--no-wait",
    is_flag=True,
    help="Do not wait for server health check; start and return immediately.",
)
@click.option(
    "--dry-run", is_flag=True, help="Print the command and exit without launching."
)
def kg_serve(
    db: str,
    dataset: str,
    port: int,
    java_opts: str | None,
    no_wait: bool,
    dry_run: bool,
) -> None:
    """Serve the local TDB2 store with Fuseki."""

    if not dataset.startswith("/"):
        raise click.BadParameter("dataset must start with '/'")
    cmd = fuseki.build_fuseki_cmd(Path(db), dataset, port, java_opts)
    if dry_run:
        click.echo(" ".join(cmd))
        return
    try:
        proc = fuseki.start_fuseki(
            Path(db), dataset=dataset, port=port, wait=not no_wait, java_opts=java_opts
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Fuseki running at http://localhost:{port}{dataset}/sparql")
    if no_wait:
        return
    try:
        proc.wait()
    except KeyboardInterrupt:
        click.echo("Stopping Fuseki...")
        proc.terminate()


@click.command(name="kg-query")
@policy.require_role("reader")
@policy.enforce
@click.option(
    "--endpoint", default="http://localhost:3030/ear/sparql", show_default=True
)
@click.option(
    "--file", "-f", type=click.Path(exists=True), help="SPARQL query file (.rq)"
)
@click.option("--sparql", "-q", help="Inline SPARQL query string")
@click.option(
    "--form",
    type=click.Choice(["select", "ask", "construct"]),
    default="select",
    show_default=True,
)
@click.option(
    "--out",
    "-o",
    type=click.Path(),
    default="data/query_results.json",
    show_default=True,
    help="Output file (.json for SELECT/ASK; .nt for CONSTRUCT)",
)
def kg_query(
    endpoint: str, file: str | None, sparql: str | None, form: str, out: str
) -> None:
    """Run a SPARQL query against the Fuseki endpoint and write results to data."""

    if bool(file) == bool(sparql):
        raise click.UsageError("Provide exactly one of --file or --sparql")
    query = Path(file).read_text(encoding="utf-8") if file else sparql
    if form == "construct" and out == "data/query_results.json":
        out = "data/construct.nt"
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    client_cls: type[Any] = _resolve_sparql_client()
    client = client_cls(endpoint)
    try:
        if form == "select":
            data = client.select(query)
            out_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            click.echo(f"{len(data.get('results', {}).get('bindings', []))} rows")
        elif form == "ask":
            boolean = client.ask(query)
            out_path.write_text(json.dumps({"boolean": boolean}), encoding="utf-8")
            click.echo(str(boolean))
        else:
            text = client.construct(query)
            out_path.write_text(text, encoding="utf-8")
            click.echo(f"Wrote {out_path}")
    except RuntimeError as exc:
        raise click.ClickException(str(exc))


@click.command(name="kg-emit")
@click.option(
    "--sources",
    "-s",
    multiple=True,
    type=click.Choice(["ear", "nsf"]),
    required=True,
    help="Repeatable: e.g., -s ear -s nsf",
)
@click.option(
    "--in",
    "in_dir",
    "-i",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Input data directory.",
)
@click.option(
    "--out",
    "out_dir",
    "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data") / "kg",
    show_default=True,
    help="Output directory for TTL files.",
)
def kg_emit(sources: tuple[str, ...], in_dir: Path, out_dir: Path) -> None:
    """Emit RDF/Turtle for selected sources."""

    out_dir.mkdir(parents=True, exist_ok=True)
    for src in sources:
        try:
            if src == "ear":
                out_path, count = emit_ear(in_dir, out_dir)
            elif src == "nsf":
                out_path, count = emit_nsf(in_dir, out_dir)
            else:
                raise click.ClickException(f"Unknown source: {src}")
            click.echo(f"{src}: {count} triples -> {out_path}")
        except Exception as exc:
            raise click.ClickException(str(exc))


@click.command(name="validate", context_settings={"allow_extra_args": True})
@click.pass_context
@click.option(
    "--ttl",
    "ttls",
    multiple=True,
    type=click.Path(path_type=Path),
    help="Path to TTL file.",
)
@click.option(
    "--glob",
    "glob_pattern",
    type=str,
    help="Glob pattern for TTL files. On Windows the shell may expand"
    " wildcards; extra paths are captured automatically.",
)
@click.option(
    "--shapes",
    type=click.Path(path_type=Path),
    default=None,
    show_default=False,
    help="Path to SHACL shapes graph.",
)
@click.option(
    "--fail-on",
    type=click.Choice(["any", "shacl-only", "sparql-only", "supported"]),
    default="any",
    show_default=True,
    help="What violations trigger a non-zero exit code.",
)
@click.option(
    "--blocking-check",
    "blocking_checks",
    multiple=True,
    type=str,
    help=(
        "SPARQL check name to treat as release-blocking when --fail-on supported "
        "(repeatable). Defaults to the supported built-in check set."
    ),
)
def kg_validate(
    ctx: click.Context,
    ttls: tuple[Path, ...],
    glob_pattern: str | None,
    shapes: Path | None,
    fail_on: str,
    blocking_checks: tuple[str, ...],
) -> None:
    """Validate emitted Turtle files using SPARQL checks and SHACL."""

    _validate_ttls(ctx, ttls, glob_pattern, shapes, fail_on, blocking_checks)


def register_kg_commands(root: click.Group) -> None:
    """Register KG-related commands on the root CLI."""

    kg_group.add_command(kg_export, name="export")
    kg_group.add_command(kg_load, name="load")
    kg_group.add_command(kg_serve, name="serve")
    kg_group.add_command(kg_query, name="query")
    kg_group.add_command(kg_emit, name="emit")
    kg_group.add_command(kg_validate, name="validate")

    root.add_command(kg_group, name="kg")
    root.add_command(kg_export)
    root.add_command(kg_load)
    root.add_command(kg_serve)
    root.add_command(kg_query)
    root.add_command(kg_emit)
    root.add_command(kg_validate, name="kg-validate")
