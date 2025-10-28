from __future__ import annotations

import json
from pathlib import Path

import click

from earCrawler.utils import retention
from earCrawler.security import policy


@click.command()
@policy.require_role("operator")
@policy.enforce
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Preview without deleting.")
@click.option("--apply", "apply", is_flag=True, default=False, help="Delete files.")
@click.option("--yes", is_flag=True, help="Confirm deletions without prompt.")
@click.option(
    "--target",
    type=click.Choice(["telemetry", "cache", "kg", "audit", "bundle", "all"]),
    default="all",
)
@click.option("--max-age", type=int, default=None, help="Override max age in days.")
@click.option("--max-mb", type=int, default=None, help="Override total size limit in MB.")
@click.option("--keep-last", type=int, default=None, help="Override keep_last_n policy.")
def gc(
    dry_run: bool,
    apply: bool,
    yes: bool,
    target: str,
    max_age: int | None,
    max_mb: int | None,
    keep_last: int | None,
) -> None:
    """Garbage collect caches, telemetry, or KG artifacts."""
    if dry_run == apply:
        raise click.UsageError("Specify exactly one of --dry-run or --apply")
    if apply and not yes and not click.confirm("Apply GC and delete files?"):
        click.echo("Aborted")
        return
    report = retention.run_gc(
        target=target,
        dry_run=dry_run,
        max_days=max_age,
        max_total_mb=max_mb,
        keep_last_n=keep_last,
    )
    report_dir = Path("kg/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "gc-report.json"
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    count = len(report["deleted"] if apply else report["candidates"])
    click.echo(f"{count} files {'deleted' if apply else 'would be deleted'}")
