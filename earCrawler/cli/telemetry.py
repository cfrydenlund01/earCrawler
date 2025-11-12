from __future__ import annotations

import json
from pathlib import Path
import shutil

import click

from earCrawler.telemetry import config as tconfig
from earCrawler.telemetry.events import cli_run
from earCrawler.telemetry.sink_file import FileSink


@click.group()
def telemetry() -> None:
    """Manage telemetry configuration."""


@telemetry.command()
def enable() -> None:
    cfg = tconfig.load_config()
    cfg.enabled = True
    tconfig.save_config(cfg)
    click.echo("Telemetry enabled")


@telemetry.command()
def disable() -> None:
    cfg = tconfig.load_config()
    cfg.enabled = False
    tconfig.save_config(cfg)
    click.echo("Telemetry disabled")


@telemetry.command()
def status() -> None:
    cfg = tconfig.load_config()
    sink = FileSink(cfg)
    data = {
        "enabled": cfg.enabled,
        "spool_dir": cfg.spool_dir,
        "files": [p.name for p in Path(cfg.spool_dir).glob("*")],
        "recent": sink.tail(5),
    }
    click.echo(json.dumps(data, indent=2, sort_keys=True))


@telemetry.command()
def test() -> None:
    cfg = tconfig.load_config()
    sink = FileSink(cfg)
    ev = cli_run("telemetry-test", 0, 0)
    path = sink.write(ev)
    click.echo(str(path))


@telemetry.command()
@click.option("--yes", is_flag=True, help="Skip confirmation.")
def purge(yes: bool) -> None:
    cfg = tconfig.load_config()
    path = Path(cfg.spool_dir)
    if not yes and not click.confirm(f"Delete telemetry spool at {path}?"):
        click.echo("Aborted")
        return
    for p in path.glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)
        elif p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    click.echo("Telemetry spool cleared")


@click.command(name="crash-test")
def crash_test() -> None:
    cfg = tconfig.load_config()
    sink = FileSink(cfg)
    from earCrawler.telemetry.events import crash_report

    sink.write(crash_report("crash-test", "RuntimeError"))
    raise RuntimeError("crash test")
