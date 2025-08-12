from __future__ import annotations

"""Validate emitted Turtle files using SPARQL checks and SHACL.

API keys for external services must be stored in Windows Credential Manager or
provided via environment variables; never embed secrets in code or tests.
"""

from glob import glob
from pathlib import Path
from typing import List

import click

from earCrawler.kg.validate import validate_files


@click.command()
@click.option("--ttl", "ttls", multiple=True, type=click.Path(path_type=Path), help="Path to TTL file.")
@click.option("--glob", "glob_pattern", type=str, help="Glob pattern for TTL files.")
@click.option(
    "--shapes",
    type=click.Path(path_type=Path),
    default=Path(__file__).resolve().parent.parent / "earCrawler" / "kg" / "shapes.ttl",
    show_default=True,
    help="Path to SHACL shapes graph.",
)
@click.option(
    "--fail-on",
    type=click.Choice(["any", "shacl-only", "sparql-only"]),
    default="any",
    show_default=True,
    help="What violations trigger a non-zero exit code.",
)
def main(ttls: tuple[Path, ...], glob_pattern: str | None, shapes: Path, fail_on: str) -> None:
    """Entry point for ``kg-validate`` CLI."""

    paths: List[str] = []
    if glob_pattern:
        paths.extend(glob(glob_pattern))
    paths.extend(str(p) for p in ttls)
    exit_code = validate_files(paths, str(shapes), fail_on=fail_on)
    raise SystemExit(exit_code)


if __name__ == "__main__":  # pragma: no cover
    main()
