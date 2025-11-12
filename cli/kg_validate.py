from __future__ import annotations

"""Validate emitted Turtle files using SPARQL checks and SHACL.

API keys for external services must be stored in Windows Credential Manager or
provided via environment variables; never embed secrets in code or tests.
"""

from pathlib import Path
from typing import List

import click
from importlib import resources

from earCrawler.kg.validate import validate_files


@click.command(context_settings={"allow_extra_args": True})
@click.pass_context
@click.option(
    "--ttl",
    "ttls",
    multiple=True,
    type=click.Path(path_type=Path),
    help="Path to TTL file.",
)
@click.option(
    "--glob",
    "glob_pattern",
    type=str,
    help="Glob pattern for TTL files. On Windows the shell may expand"
    " wildcards; extra paths are captured automatically.",
)
@click.option(
    "--shapes",
    type=click.Path(path_type=Path),
    default=None,
    show_default=False,
    help="Path to SHACL shapes graph.",
)
@click.option(
    "--fail-on",
    type=click.Choice(["any", "shacl-only", "sparql-only"]),
    default="any",
    show_default=True,
    help="What violations trigger a non-zero exit code.",
)
def main(
    ctx: click.Context,
    ttls: tuple[Path, ...],
    glob_pattern: str | None,
    shapes: Path | None,
    fail_on: str,
) -> None:
    """Entry point for ``kg-validate`` CLI."""

    paths: List[str] = []
    if glob_pattern:
        if ctx.args:
            # ``glob_pattern`` is the first expanded file; remaining files are
            # stored in ``ctx.args`` when the shell performs wildcard expansion
            # (common on Windows).  Treat them all as direct file paths.
            paths.extend([glob_pattern, *ctx.args])
        else:
            pattern_path = Path(glob_pattern)
            paths.extend(str(p) for p in pattern_path.parent.glob(pattern_path.name))
    paths.extend(str(p) for p in ttls)

    if shapes is None:
        with resources.as_file(
            resources.files("earCrawler.kg").joinpath("shapes.ttl")
        ) as default_shapes:
            exit_code = validate_files(paths, default_shapes, fail_on=fail_on)
    else:
        exit_code = validate_files(paths, shapes, fail_on=fail_on)
    raise SystemExit(exit_code)


if __name__ == "__main__":  # pragma: no cover
    main()
