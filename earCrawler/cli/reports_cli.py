import click
from tabulate import tabulate
from earCrawler.analytics.reports import ReportsGenerator, AnalyticsError

@click.group()
def main():
    """EAR analytics reports."""
    pass

@main.command()
def countries():
    """Show entity counts grouped by country."""
    try:
        gen = ReportsGenerator()
        data = gen.count_entities_by_country()
        rows = sorted(data.items())
        click.echo(tabulate(rows, headers=["Country", "Count"]))
    except AnalyticsError as exc:
        raise click.ClickException(str(exc))

@main.command()
def years():
    """Show document counts grouped by year."""
    try:
        gen = ReportsGenerator()
        data = gen.count_documents_by_year()
        rows = sorted(data.items())
        click.echo(tabulate(rows, headers=["Year", "Count"]))
    except AnalyticsError as exc:
        raise click.ClickException(str(exc))

@main.command(name="entity-docs")
@click.argument("entity_id")
def entity_docs(entity_id: str):
    """Show document count for ENTITY_ID."""
    try:
        gen = ReportsGenerator()
        count = gen.get_document_count_for_entity(entity_id)
        click.echo(str(count))
    except AnalyticsError as exc:
        raise click.ClickException(str(exc))

if __name__ == "__main__":
    main()
