from __future__ import annotations

"""Top-level CLI exposing NSF parser and reports commands."""

import json
from pathlib import Path

import click

from earCrawler.core.nsf_case_parser import NSFCaseParser
from . import reports_cli
from earCrawler.analytics import reports as analytics_reports


@click.group()
def cli() -> None:  # pragma: no cover - simple wrapper
    """earCrawler command line."""


@cli.command(name="nsf-parse")
@click.option(
    "--fixtures",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory containing ORI HTML fixtures.",
)
@click.option(
    "--out",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Output directory for parsed cases.",
)
@click.option("--live", default=False, show_default=True, type=bool)
def nsf_parse(fixtures: Path, out: Path, live: bool) -> None:
    """Parse NSF/ORI case files to JSON."""
    parser = NSFCaseParser()
    cases = parser.run(fixtures, live=live)
    out.mkdir(parents=True, exist_ok=True)
    for case in cases:
        case_id = case.get("case_number") or f"case_{cases.index(case)}"
        with (out / f"{case_id}.json").open("w", encoding="utf-8") as fh:
            json.dump(case, fh, ensure_ascii=False, indent=2)
    click.echo(f"Parsed {len(cases)} cases")


# Expose existing reports commands under "reports" group
cli.add_command(reports_cli.reports, name="reports")


@cli.command(name="crawl")
@click.option(
    "--sources",
    "-s",
    multiple=True,
    metavar="[SOURCE1 [SOURCE2]...]",
    required=True,
    help="Which corpus loaders to run (ear, nsf, ...).",
)
@click.option(
    "--out",
    "-o",
    type=str,
    default="data",
    show_default=True,
    help="Output directory for JSONL/index files.",
)
@click.option(
    "--fixtures",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("tests/fixtures"),
    show_default=True,
    help="Fixture directory for NSF loader.",
)
@click.option("--live", is_flag=True, default=False, help="Enable live HTTP fetching (disabled by default).")
def crawl(sources: tuple[str, ...], out: str, fixtures: Path, live: bool) -> None:
    """Load paragraphs from selected sources and print counts."""
    from api_clients.federalregister_client import FederalRegisterClient
    from earCrawler.core.ear_loader import EARLoader
    from earCrawler.core.nsf_loader import NSFLoader

    total = 0
    if "ear" in sources:
        client = FederalRegisterClient()
        loader = EARLoader(client, query="export administration regulations")
        count = len(loader.run(fixtures_dir=fixtures, live=live, output_dir=out))
        click.echo(f"ear: {count} paragraphs")
        total += count
    if "nsf" in sources:
        parser = NSFCaseParser()
        loader = NSFLoader(parser, fixtures)
        count = len(loader.run(fixtures_dir=fixtures, live=live, output_dir=out))
        click.echo(f"nsf: {count} paragraphs")
        total += count
    click.echo(f"total: {total} paragraphs")


@cli.command(name="report")
@click.option(
    "--sources",
    "-s",
    multiple=True,
    required=True,
    help="Sources to analyze (ear, nsf, ...).",
)
@click.option(
    "--type",
    "report_type",
    type=click.Choice(["top-entities", "term-frequency", "cooccurrence"]),
    required=True,
    help="Type of report to generate.",
)
@click.option(
    "--entity",
    "entity_type",
    type=click.Choice(["ORG", "PERSON", "GRANT"]),
    required=False,
    help="Entity type (for top-entities and cooccurrence reports).",
)
@click.option("--n", default=10, show_default=True, help="Top n entries to return.")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Write JSON output to file instead of stdout.",
)
def report(
    sources: tuple[str, ...],
    report_type: str,
    entity_type: str | None,
    n: int,
    out: Path | None,
) -> None:
    """Generate analytics reports over stored corpora."""
    results: dict[str, object] = {}
    for src in sources:
        if report_type == "top-entities":
            if entity_type is None:
                raise click.UsageError("--entity required for top-entities")
            results[src] = analytics_reports.top_entities(src, entity_type, n)
        elif report_type == "term-frequency":
            results[src] = analytics_reports.term_frequency(src, n)
        elif report_type == "cooccurrence":
            if entity_type is None:
                raise click.UsageError("--entity required for cooccurrence")
            mapping = analytics_reports.cooccurrence(src, entity_type)
            results[src] = {k: sorted(v) for k, v in mapping.items()}

    if out:
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    for src, data in results.items():
        click.echo(f"## {src}")
        if report_type == "cooccurrence":
            for name, others in data.items():
                click.echo(f"{name}\t{', '.join(others)}")
        else:
            for name, count in data:
                click.echo(f"{name}\t{count}")


@cli.command(name="kg-export")
@click.option("--data-dir", default="data", help="Crawl JSONL directory.")
@click.option("--out-ttl", default="kg/ear_triples.ttl", help="Output TTL file.")
@click.option(
    "--live/--offline",
    default=False,
    help="If --live, verify Java env before exporting TTL.",
)
def kg_export(data_dir: str, out_ttl: str, live: bool) -> None:
    """Export paragraphs & entities to Turtle for Jena TDB2."""
    from pathlib import Path
    from earCrawler.kg.triples import export_triples

    export_triples(Path(data_dir), Path(out_ttl), live=live)
    click.echo(f"Written triples to {out_ttl}")


@click.command()
@click.option("--ttl", "-t", default="kg/ear_triples.ttl", help="Turtle file to load.")
@click.option("--db", "-d", default="db", help="TDB2 DB directory.")
def kg_load(ttl: str, db: str) -> None:
    """Load Turtle into Jena TDB2 store."""
    from pathlib import Path
    from earCrawler.kg.loader import load_tdb

    load_tdb(Path(ttl), Path(db))
    click.echo(f"Loaded {ttl} into TDB2 at {db}")


cli.add_command(kg_load, name="kg-load")


def main() -> None:  # pragma: no cover - CLI entrypoint
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
