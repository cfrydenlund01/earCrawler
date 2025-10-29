from __future__ import annotations

from pathlib import Path

import click

from earCrawler.cli.bundle import build as bundle_build, verify as bundle_verify, export_profiles_cmd
from earCrawler.cli.jobs import run_job_internal
from earCrawler.kg.integrity import check_file
from earCrawler.monitor.run_logger import run_logger
from earCrawler.perf.bench import run_benchmarks
from earCrawler.security import policy


@click.group()
@policy.require_role("operator", "maintainer")
@policy.enforce
def admin() -> None:
    """Administrative helpers for Windows scheduler."""


@admin.command()
@click.option("--canonical", type=click.Path(path_type=Path), default=Path("kg/canonical"))
@click.option("--out", type=click.Path(path_type=Path), default=Path("dist/offline_bundle"))
def build(canonical: Path, out: Path) -> None:
    bundle_build.callback(canonical=canonical)  # type: ignore[attr-defined]
    click.echo(f"Bundle staged under {out}")


@admin.command()
@click.argument("ttl", type=click.Path(path_type=Path))
@click.option("--manifest", is_flag=True, help="print manifest of issues")
def validate(ttl: Path, manifest: bool) -> None:
    issues = check_file(ttl)
    for issue in issues:
        click.echo(f"{issue.name}: {issue.count}")
    violations = [i for i in issues if i.count > 0]
    if violations:
        raise click.ClickException("Integrity violations detected")
    if manifest:
        click.echo("Integrity manifest clean")


@admin.command()
@click.option("--ttl", type=click.Path(path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path), default=Path("dist/exports"))
@click.option("--stem", default="dataset")
def export(ttl: Path, out: Path, stem: str) -> None:
    export_profiles_cmd.callback(ttl=ttl, out=out, stem=stem)  # type: ignore[attr-defined]


@admin.command()
@click.argument("job", type=click.Choice(["tradegov", "federalregister"]))
@click.option("--dry-run", is_flag=True)
@click.option("--quiet", is_flag=True)
def load(job: str, dry_run: bool, quiet: bool) -> None:
    summary = run_job_internal(job, dry_run, quiet)
    click.echo(f"Job summary written to {summary}")


@admin.command()
@click.option("--out", type=click.Path(path_type=Path), default=Path("run/logs/bench.json"))
@click.option("--iterations", default=1, show_default=True)
@click.option("--fixtures", type=click.Path(path_type=Path), default=Path("tests/fixtures"))
def stats(out: Path, iterations: int, fixtures: Path) -> None:
    stats = run_benchmarks(fixtures, iterations=iterations)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(stats.to_json(), encoding="utf-8")
    click.echo(out.read_text())
