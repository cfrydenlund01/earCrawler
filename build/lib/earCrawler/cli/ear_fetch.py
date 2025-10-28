"""CLI commands for interacting with Trade.gov and Federal Register APIs."""
from __future__ import annotations

import json
from pathlib import Path

import click

from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.kg.loader import enrich_entities_with_tradegov
from earCrawler.kg.emit_ear import fetch_ear_corpus


@click.command(name="fetch-entities")
@click.option("--name", required=True, help="Entity name to lookup")
def fetch_entities(name: str) -> None:
    """Lookup an entity using Trade.gov and print normalized JSON."""
    client = TradeGovClient()
    record = client.lookup_entity(name)
    click.echo(json.dumps(record, ensure_ascii=False, indent=2))


@click.command(name="fetch-ear")
@click.option("--term", required=True, help="Search term for EAR articles")
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=Path("kg/source/ear"),
    show_default=True,
    help="Output directory for EAR corpus JSONL",
)
def fetch_ear(term: str, out_dir: Path) -> None:
    """Fetch EAR corpus for ``term`` and write JSONL."""
    client = FederalRegisterClient()
    fetch_ear_corpus(term, client=client, out_dir=out_dir)
    click.echo(f"Fetched EAR corpus for '{term}'")


@click.command(name="warm-cache")
def warm_cache() -> None:
    """Preload API cache for common queries."""
    tg = TradeGovClient()
    fr = FederalRegisterClient()
    enrich_entities_with_tradegov([{"name": "Acme Corp"}], tg)
    fetch_ear_corpus("export", fr)
    click.echo("Caches warmed")


__all__ = ["fetch_entities", "fetch_ear", "warm_cache"]
