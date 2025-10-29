from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click

from earCrawler.monitor.run_logger import log_step, run_logger
from earCrawler.security import policy


def _python_exe() -> str:
    return sys.executable


def _logs_dir() -> Path:
    path = Path("run/logs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_cli(args: list[str], *, quiet: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run([_python_exe(), "-m", "earCrawler.cli", *args], capture_output=quiet, text=True)


@click.group()
@policy.require_role("operator", "maintainer")
@policy.enforce
def jobs() -> None:
    """Scheduler-friendly job helpers."""


def run_job_internal(job: str, dry_run: bool, quiet: bool) -> Path:
    logs = _logs_dir()
    run_id = f"{job}-{uuid.uuid4().hex[:8]}"
    summary_path = logs / f"{run_id}.json"

    with run_logger(summary_path, run_id=run_id) as run:
        run.input_hash = datetime.now(timezone.utc).strftime("%Y%m%d")
        if job == "tradegov":
            _execute_tradegov(run, dry_run, quiet)
        else:
            _execute_federalregister(run, dry_run, quiet)
    return summary_path


@jobs.command("run")
@click.argument("job", type=click.Choice(["tradegov", "federalregister"]))
@click.option("--dry-run", is_flag=True, help="Skip network calls and run validations only")
@click.option("--quiet", is_flag=True, help="Suppress stdout from child commands")
def run_job(job: str, dry_run: bool, quiet: bool) -> None:
    run_job_internal(job, dry_run, quiet)


def _execute_tradegov(run, dry_run: bool, quiet: bool) -> None:
    crawl_args = ["crawl", "-s", "ear", "--out", "data"]
    if dry_run:
        crawl_args += ["--fixtures", "tests/fixtures"]
    else:
        crawl_args.append("--live")
    _run_step(run, "crawl", crawl_args, quiet=quiet, dry_run=False)

    bundle_args = ["bundle", "build"]
    _run_step(run, "bundle-build", bundle_args, quiet=quiet, dry_run=dry_run)


def _execute_federalregister(run, dry_run: bool, quiet: bool) -> None:
    crawl_args = ["crawl", "-s", "ear", "--out", "data"]
    if dry_run:
        crawl_args += ["--fixtures", "tests/fixtures"]
    else:
        crawl_args.append("--live")
    _run_step(run, "crawl", crawl_args, quiet=quiet, dry_run=False)

    _run_step(run, "bundle-verify", ["bundle", "verify"], quiet=quiet, dry_run=dry_run)


def _run_step(run, name: str, args: list[str], *, quiet: bool, dry_run: bool) -> None:
    metadata = {"command": " ".join(["earCrawler.cli"] + args)}
    with log_step(run, name, metadata=metadata) as meta:
        if dry_run:
            meta["skipped"] = "true"
            return
        result = _run_cli(args, quiet=quiet)
        meta["returncode"] = str(result.returncode)
        if result.returncode != 0:
            raise click.ClickException(f"Command failed: {' '.join(args)}")
