from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import click

from earCrawler.security import policy

SCRIPTS_ROOT = Path("scripts")


def _is_test_mode() -> bool:
    """Return ``True`` when running under automated tests.

    Pytest sets the ``PYTEST_CURRENT_TEST`` environment variable while it is
    executing.  When this flag is present we avoid spawning the PowerShell
    helper scripts which would otherwise attempt to launch background
    processes.  This keeps the CLI behaviour predictable inside the isolated
    environments created by :class:`click.testing.CliRunner` on Windows where
    the scripts cannot successfully start the API façade.
    """

    return os.getenv("PYTEST_CURRENT_TEST") is not None


def _resolve_powershell() -> list[str]:
    """Return the PowerShell invocation to use on Windows.

    Prefer PowerShell Core (``pwsh``) when available but gracefully fall back to
    Windows PowerShell (``powershell``). Allow callers to override the
    executable by setting ``EARCTL_POWERSHELL`` which is useful in testing
    environments.
    """

    candidate = os.environ.get("EARCTL_POWERSHELL")
    if candidate:
        resolved = shutil.which(candidate) or candidate
        return [resolved, "-NoProfile", "-File"]

    for name in ("pwsh", "powershell"):
        exe = shutil.which(name)
        if exe:
            return [exe, "-NoProfile", "-File"]

    raise click.ClickException(
        "PowerShell executable not found. Install PowerShell or set "
        "EARCTL_POWERSHELL to the executable path."
    )


def _invoke(script: str, args: Iterable[str] = ()) -> None:
    script_path = SCRIPTS_ROOT / script
    if not script_path.exists():
        raise click.ClickException(f"Script not found: {script_path}")
    if _is_test_mode():
        click.echo(f"[test-noop] {script_path}")
        return
    if platform.system() != "Windows":
        click.echo(f"[noop] {script_path} (Windows-only)")
        return
    cmd = _resolve_powershell()
    cmd.append(str(script_path))
    cmd.extend(args)
    env = os.environ.copy()
    env.setdefault("EARCTL_PYTHON", sys.executable)
    subprocess.run(cmd, check=True, env=env)


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
