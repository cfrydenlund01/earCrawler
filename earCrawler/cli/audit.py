from __future__ import annotations

import json
from pathlib import Path
import click

from earCrawler.audit.hitl_events import ingest_hitl_directory
from earCrawler.audit import ledger, verify
from earCrawler.security import policy


@click.group()
@policy.require_role("operator", "admin")
def audit() -> None:
    """Audit ledger utilities."""


@audit.command(name="verify")
@click.option("--path", type=click.Path(path_type=Path), default=None)
@policy.enforce
def verify_cmd(path: Path | None) -> None:
    path = path or ledger.current_log_path()
    ok = verify.verify(path)
    click.echo(json.dumps({"path": str(path), "ok": ok}))
    if not ok:
        raise click.ClickException("audit verification failed")


@audit.command(name="rotate")
@policy.enforce
def rotate_cmd() -> None:
    p = ledger.rotate()
    click.echo(str(p))


@audit.command(name="tail")
@click.option("--n", type=int, default=50)
@policy.enforce
def tail_cmd(n: int) -> None:
    entries = list(ledger.tail(n))
    for e in entries:
        click.echo(json.dumps(e))


@audit.command(name="ingest-hitl")
@click.argument("directory", type=click.Path(path_type=Path, exists=True, file_okay=False))
@policy.enforce
def ingest_hitl_cmd(directory: Path) -> None:
    """Ingest filled HITL decision templates into the audit ledger."""

    try:
        summary = ingest_hitl_directory(directory)
    except Exception as exc:
        raise click.ClickException(str(exc))
    click.echo(json.dumps(summary))
