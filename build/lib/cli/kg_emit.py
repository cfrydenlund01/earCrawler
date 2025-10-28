from __future__ import annotations

"""Emit EAR/NSF corpora to Turtle files.

Secrets such as Trade.gov or Federal Register API keys must be stored in
Windows Credential Manager or provided via environment variables, never
hard-coded.
"""

from pathlib import Path

import click

from earCrawler.kg.emit_ear import emit_ear
from earCrawler.kg.emit_nsf import emit_nsf


@click.command()
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
def main(sources: tuple[str, ...], in_dir: Path, out_dir: Path) -> None:
    """Emit RDF/Turtle for selected sources."""

    out_dir.mkdir(parents=True, exist_ok=True)
    for src in sources:
        try:
            if src == "ear":
                out_path, count = emit_ear(in_dir, out_dir)
            elif src == "nsf":
                out_path, count = emit_nsf(in_dir, out_dir)
            else:  # pragma: no cover - click restricts choices
                raise click.ClickException(f"Unknown source: {src}")
            click.echo(f"{src}: {count} triples -> {out_path}")
        except Exception as exc:  # pragma: no cover - runtime errors
            raise click.ClickException(str(exc))


if __name__ == "__main__":  # pragma: no cover
    main()
