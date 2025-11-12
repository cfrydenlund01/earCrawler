from __future__ import annotations

"""CLI group for curated corpus workflows."""

from pathlib import Path

import click

from earCrawler.corpus import build_corpus, validate_corpus, snapshot_corpus
from earCrawler.security import policy


@click.group()
@policy.require_role("operator", "maintainer")
@policy.enforce
def corpus() -> None:
    """Build, validate, and snapshot curated corpora."""


@corpus.command("build")
@click.option(
    "-s",
    "--source",
    "sources",
    multiple=True,
    type=click.Choice(["ear", "nsf"]),
    help="Sources to include (defaults to both).",
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Output directory for corpus files.",
)
@click.option(
    "--fixtures",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("tests/fixtures"),
    show_default=True,
    help="Fixture directory when not running live.",
)
@click.option(
    "--live",
    is_flag=True,
    default=False,
    help="Fetch data from live sources instead of fixtures.",
)
def build_cmd(
    sources: tuple[str, ...], out_dir: Path, fixtures: Path, live: bool
) -> None:
    """Materialize curated JSONL corpora."""

    try:
        manifest = build_corpus(
            list(sources), out_dir, live, fixtures if not live else None
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    summary = manifest.get("summary", {})
    for file_info in manifest.get("files", []):
        name = file_info["name"]
        count = file_info["records"]
        digest = file_info["sha256"][:12]
        click.echo(f"{name}: {count} records (sha256={digest})")
    if summary:
        items = ", ".join(f"{src}={count}" for src, count in summary.items())
        click.echo(f"Summary: {items}")
    click.echo(f"Manifest written to {out_dir / 'manifest.json'}")


@corpus.command("validate")
@click.option(
    "--dir",
    "data_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Data directory containing corpus files.",
)
def validate_cmd(data_dir: Path) -> None:
    """Validate required provenance and schema."""

    problems = validate_corpus(data_dir)
    if problems:
        for problem in problems:
            click.echo(problem, err=True)
        raise click.ClickException(f"{len(problems)} validation issue(s) detected")
    click.echo(f"Corpus under {data_dir} passed validation")


@corpus.command("snapshot")
@click.option(
    "--dir",
    "data_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Data directory containing corpus files.",
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("dist") / "corpus",
    show_default=True,
    help="Base directory where snapshots will be stored.",
)
def snapshot_cmd(data_dir: Path, out_dir: Path) -> None:
    """Copy corpus artifacts into a timestamped snapshot."""

    target = snapshot_corpus(data_dir, out_dir)
    click.echo(f"Snapshot created at {target}")


__all__ = ["corpus"]
