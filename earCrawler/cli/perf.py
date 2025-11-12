from __future__ import annotations

import subprocess
from pathlib import Path

import click

from earCrawler.security import policy
from perf.synth.generator import generate
from earCrawler.utils import perf_report


@click.group()
def perf() -> None:  # pragma: no cover - thin wrapper
    """Performance tooling commands."""


@perf.command()
@click.option("--scale", type=click.Choice(["S", "M"]), default="S")
@policy.require_role("operator")
@policy.enforce
def synth(scale: str) -> None:
    """Generate synthetic dataset."""
    generate(scale)
    click.echo(f"generated synthetic dataset for scale {scale}")


@perf.command()
@click.option("--scale", type=click.Choice(["S", "M"]), default="S")
@click.option("--cold", is_flag=True, default=False)
@click.option("--warm", is_flag=True, default=False)
@policy.require_role("operator")
@policy.enforce
def run(scale: str, cold: bool, warm: bool) -> None:
    """Run performance tests via PowerShell script."""
    cmd = ["pwsh", "-File", "kg/scripts/perf-run.ps1", "-Scale", scale]
    if cold:
        cmd.append("-Cold")
    if warm:
        cmd.append("-Warm")
    subprocess.run(cmd, check=True)


@perf.command()
@click.option(
    "--baseline",
    type=click.Path(path_type=Path),
    default=Path("perf/baselines/baseline_S.json"),
)
@click.option(
    "--budgets",
    type=click.Path(path_type=Path),
    default=Path("perf/config/perf_budgets.yml"),
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    default=Path("kg/reports/perf-report.json"),
)
@click.option("--scale", type=click.Choice(["S", "M"]), default="S")
@policy.require_role("maintainer")
@policy.enforce
def gate(baseline: Path, budgets: Path, report: Path, scale: str) -> None:
    """Compare report to baseline and enforce budgets."""
    passed, _ = perf_report.gate(report, baseline, budgets, scale)
    if not passed:
        raise click.ClickException("performance gate failed")
    click.echo("performance gate passed")


@perf.command()
@click.option("--open", "show", is_flag=True, default=False, help="Print summary paths")
@policy.require_role("operator")
@policy.enforce
def report(show: bool) -> None:
    """Print locations of performance reports."""
    if show:
        click.echo("kg/reports/perf-report.json")
        click.echo("kg/reports/perf-summary.txt")


__all__ = ["perf"]
