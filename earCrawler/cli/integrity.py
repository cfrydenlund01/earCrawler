from __future__ import annotations

from pathlib import Path

import click

from earCrawler.kg.integrity import check_file
from earCrawler.security import policy


@click.group()
@policy.require_role("operator", "maintainer")
@policy.enforce
def integrity() -> None:
    """Run KG integrity checks."""


@integrity.command("check")
@click.argument("ttl", type=click.Path(path_type=Path))
def check(ttl: Path) -> None:
    if not ttl.exists():
        raise click.ClickException(f"TTL file not found: {ttl}")
    issues = check_file(ttl)
    failed = [issue for issue in issues if issue.count > 0]
    for issue in issues:
        click.echo(f"{issue.name}: {issue.count}")
    if failed:
        raise click.ClickException("Integrity violations detected")
    click.echo("Integrity checks passed")
