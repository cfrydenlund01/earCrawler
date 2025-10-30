from __future__ import annotations

import uuid
from pathlib import Path

import click

from earCrawler.cli.bundle import build as bundle_build
from earCrawler.cli.jobs import run_job_internal
from earCrawler.kg.integrity import check_file
from earCrawler.kg.export_profiles import export_profiles
from earCrawler.monitor.run_logger import log_step, run_logger
from earCrawler.perf.bench import run_benchmarks
from earCrawler.security import policy


@click.group()
@policy.require_role("operator", "maintainer")
@policy.enforce
def admin() -> None:
    """Administrative helpers for Windows scheduler."""


def _logs_dir() -> Path:
    path = Path("run/logs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _start_run(prefix: str) -> tuple[Path, str]:
    run_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    summary_path = _logs_dir() / f"{run_id}.json"
    return summary_path, run_id


@admin.command()
@click.option("--canonical", type=click.Path(path_type=Path), default=Path("kg/canonical"))
@click.option("--out", type=click.Path(path_type=Path), default=Path("dist/offline_bundle"))
def build(canonical: Path, out: Path) -> None:
    summary_path, run_id = _start_run("admin-build")
    with run_logger(summary_path, run_id=run_id, input_hash=str(canonical)) as run:
        with log_step(run, "bundle-build", metadata={"canonical": str(canonical)}) as meta:
            bundle_build.callback(canonical=canonical)  # type: ignore[attr-defined]
            meta["bundle_path"] = str(out)
    click.echo(f"Bundle staged under {out}")
    click.echo(f"Run summary written to {summary_path}")


@admin.command()
@click.argument("ttl", type=click.Path(path_type=Path))
@click.option("--manifest", is_flag=True, help="print manifest of issues")
def validate(ttl: Path, manifest: bool) -> None:
    summary_path, run_id = _start_run("admin-validate")
    with run_logger(summary_path, run_id=run_id, input_hash=str(ttl)) as run:
        with log_step(run, "integrity-check", metadata={"ttl": str(ttl)}) as meta:
            issues = check_file(ttl)
            for issue in issues:
                click.echo(f"{issue.name}: {issue.count}")
            violations = [i for i in issues if i.count > 0]
            meta["violations"] = str(len(violations))
            if violations:
                raise click.ClickException("Integrity violations detected")
            if manifest:
                click.echo("Integrity manifest clean")
    click.echo(f"Run summary written to {summary_path}")


@admin.command()
@click.option("--ttl", type=click.Path(path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path), default=Path("dist/exports"))
@click.option("--stem", default="dataset")
def export(ttl: Path, out: Path, stem: str) -> None:
    summary_path, run_id = _start_run("admin-export")
    with run_logger(summary_path, run_id=run_id, input_hash=str(ttl)) as run:
        with log_step(
            run,
            "export-profiles",
            metadata={"ttl": str(ttl), "out": str(out), "stem": stem},
        ) as meta:
            manifest = export_profiles(ttl, out, stem=stem)
            meta["items"] = str(len(manifest))
            click.echo(f"Exported profiles to {out} ({len(manifest)} items)")
    click.echo(f"Run summary written to {summary_path}")


@admin.command()
@click.argument("job", type=click.Choice(["tradegov", "federalregister"]))
@click.option("--dry-run", is_flag=True)
@click.option("--quiet", is_flag=True)
def load(job: str, dry_run: bool, quiet: bool) -> None:
    summary_path, run_id = _start_run("admin-load")
    with run_logger(summary_path, run_id=run_id, input_hash=job) as run:
        with log_step(
            run,
            "jobs-run",
            metadata={"job": job, "dry_run": str(dry_run).lower(), "quiet": str(quiet).lower()},
        ) as meta:
            job_summary = run_job_internal(job, dry_run, quiet)
            meta["job_summary"] = str(job_summary)
    click.echo(f"Job summary written to {job_summary}")
    click.echo(f"Run summary written to {summary_path}")


@admin.command()
@click.option("--out", type=click.Path(path_type=Path), default=Path("run/logs/bench.json"))
@click.option("--iterations", default=1, show_default=True)
@click.option("--fixtures", type=click.Path(path_type=Path), default=Path("tests/fixtures"))
def stats(out: Path, iterations: int, fixtures: Path) -> None:
    summary_path, run_id = _start_run("admin-stats")
    with run_logger(summary_path, run_id=run_id, input_hash=str(fixtures)) as run:
        with log_step(
            run,
            "benchmarks",
            metadata={"fixtures": str(fixtures), "iterations": str(iterations)},
        ) as meta:
            stats = run_benchmarks(fixtures, iterations=iterations)
            timings = getattr(stats, "timings", {})
            if timings:
                meta["timings"] = ";".join(f"{k}={round(v, 4)}" for k, v in timings.items())
        with log_step(run, "write-output", metadata={"out": str(out)}) as meta:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(stats.to_json(), encoding="utf-8")
            meta["bytes"] = str(out.stat().st_size if out.exists() else 0)
            click.echo(out.read_text())
    click.echo(f"Run summary written to {summary_path}")
