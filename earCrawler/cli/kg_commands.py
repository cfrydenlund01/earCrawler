from __future__ import annotations

"""KG CLI commands and registrar."""

import json
from pathlib import Path
from typing import Any

import click

from earCrawler.kg import emit_ear, emit_nsf, fuseki
from earCrawler.kg.sparql import SPARQLClient
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


def register_kg_commands(root: click.Group) -> None:
    """Register KG-related commands on the root CLI."""

    root.add_command(kg_export)
    root.add_command(kg_load)
    root.add_command(kg_serve)
    root.add_command(kg_query)
    root.add_command(kg_emit)
