from __future__ import annotations

import json
from pathlib import Path
import click

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
