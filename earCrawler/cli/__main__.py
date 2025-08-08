from __future__ import annotations

"""Top-level CLI exposing NSF parser and reports commands."""

import json
from pathlib import Path

import click

from earCrawler.core.nsf_case_parser import NSFCaseParser
from . import reports_cli


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


def main() -> None:  # pragma: no cover - CLI entrypoint
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
