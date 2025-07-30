from __future__ import annotations

"""Command line interface for analytics reports."""

import os
from typing import Dict, Any

import click
import requests
from tabulate import tabulate


def _get_service_url() -> str:
    """Return the analytics service base URL from ``ANALYTICS_SERVICE_URL``."""
    url = os.getenv("ANALYTICS_SERVICE_URL")
    if not url:
        raise click.ClickException(
            "ANALYTICS_SERVICE_URL environment variable not set"
        )
    return url.rstrip("/")


@click.group()
def reports() -> None:
    """Fetch analytics reports from the FastAPI service."""


@reports.command(name="entities-by-country")
def entities_by_country() -> None:
    """Display entity counts grouped by country."""
    base_url = _get_service_url()
    url = f"{base_url}/reports/entities-by-country"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "")
        click.echo(f"Request failed with status {status}", err=True)
        raise SystemExit(1)
    except requests.RequestException as exc:
        click.echo(f"Request error: {exc}", err=True)
        raise SystemExit(1)

    try:
        data = resp.json()
    except ValueError:
        click.echo("Malformed JSON response", err=True)
        raise SystemExit(1)

    mapping = data.get("entities_by_country")
    if not isinstance(mapping, dict):
        click.echo("Malformed response JSON", err=True)
        raise SystemExit(1)

    rows = sorted(mapping.items())
    click.echo(tabulate(rows, headers=["Country", "Count"]))


@reports.command(name="documents-by-year")
def documents_by_year() -> None:
    """Display document counts grouped by publication year."""
    base_url = _get_service_url()
    url = f"{base_url}/reports/documents-by-year"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "")
        click.echo(f"Request failed with status {status}", err=True)
        raise SystemExit(1)
    except requests.RequestException as exc:
        click.echo(f"Request error: {exc}", err=True)
        raise SystemExit(1)

    try:
        data = resp.json()
    except ValueError:
        click.echo("Malformed JSON response", err=True)
        raise SystemExit(1)

    mapping = data.get("documents_by_year")
    if not isinstance(mapping, dict):
        click.echo("Malformed response JSON", err=True)
        raise SystemExit(1)

    rows = sorted((str(k), v) for k, v in mapping.items())
    click.echo(tabulate(rows, headers=["Year", "Count"]))


@reports.command(name="document-count")
@click.argument("entity_id")
def document_count(entity_id: str) -> None:
    """Display number of documents associated with ``ENTITY_ID``."""
    if not entity_id or not entity_id.strip():
        click.echo("entity_id must not be empty", err=True)
        raise SystemExit(1)

    base_url = _get_service_url()
    url = f"{base_url}/reports/document-count/{entity_id}"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "")
        click.echo(f"Request failed with status {status}", err=True)
        raise SystemExit(1)
    except requests.RequestException as exc:
        click.echo(f"Request error: {exc}", err=True)
        raise SystemExit(1)

    try:
        data: Dict[str, Any] = resp.json()
    except ValueError:
        click.echo("Malformed JSON response", err=True)
        raise SystemExit(1)

    count = data.get("document_count")
    if not isinstance(count, int):
        click.echo("Malformed response JSON", err=True)
        raise SystemExit(1)

    click.echo(f"Entity {entity_id} has {count} documents")


# Read service URL from env; do not hard-code.
# Validate CLI args to prevent injection or misuse.
# Do not log or expose sensitive URLs.
if __name__ == "__main__":
    reports()
