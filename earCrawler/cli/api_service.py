from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Iterable

import click

from earCrawler.security import policy

SCRIPTS_ROOT = Path("scripts")


def _invoke(script: str, args: Iterable[str] = ()) -> None:
    script_path = SCRIPTS_ROOT / script
    if not script_path.exists():
        raise click.ClickException(f"Script not found: {script_path}")
    if platform.system() != "Windows":
        click.echo(f"[noop] {script_path} (Windows-only)")
        return
    cmd = ["pwsh", "-NoProfile", "-File", str(script_path)]
    cmd.extend(args)
    subprocess.run(cmd, check=True)


@click.group()
@policy.require_role("operator", "maintainer")
@policy.enforce
def api() -> None:
    """Manage the read-only API service."""


@api.command()
@policy.require_role("operator", "maintainer")
@policy.enforce
@click.option("--host", default=None, help="Override EARCRAWLER_API_HOST")
@click.option("--port", type=int, default=None, help="Override EARCRAWLER_API_PORT")
@click.option("--fuseki", default=None, help="Override EARCRAWLER_FUSEKI_URL")
def start(host: str | None, port: int | None, fuseki: str | None) -> None:
    """Start the API facade."""
    args = []
    if host:
        args += ["-Host", host]
    if port:
        args += ["-Port", str(port)]
    if fuseki:
        args += ["-FusekiUrl", fuseki]
    _invoke("api-start.ps1", args)


@api.command()
@policy.require_role("operator", "maintainer")
@policy.enforce
def stop() -> None:
    """Stop the API facade."""
    _invoke("api-stop.ps1")


@api.command()
@policy.require_role("operator", "maintainer")
@policy.enforce
def smoke() -> None:
    """Run API smoke tests."""
    _invoke("api-smoke.ps1")
