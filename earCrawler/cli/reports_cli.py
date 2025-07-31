"""CLI for EAR analytics reports."""

from __future__ import annotations

import click
from tabulate import tabulate

from earCrawler.analytics import ReportsGenerator


@click.group()
@click.version_option("0.1.0")
def cli() -> None:
    """Execute analytics reporting commands."""
    pass


@cli.command("entities-by-country")
def entities_by_country() -> None:
    """Display entity counts grouped by country."""
    gen = ReportsGenerator()
    data = gen.count_entities_by_country()
    rows = sorted(data.items())
    click.echo(tabulate(rows, headers=["Country", "Count"]))


@cli.command("documents-by-year")
def documents_by_year() -> None:
    """Display document counts grouped by year."""
    gen = ReportsGenerator()
    data = gen.count_documents_by_year()
    rows = sorted(data.items())
    click.echo(tabulate(rows, headers=["Year", "Count"]))


@cli.command("document-count")
@click.argument("entity_id")
def document_count(entity_id: str) -> None:
    """Display document count for ``ENTITY_ID``."""
    gen = ReportsGenerator()
    count = gen.get_document_count_for_entity(entity_id)
    click.echo(f"{entity_id}: {count}")


def main() -> None:
    """Entry point for the console script."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
