from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from earCrawler.security import policy
from earCrawler.kg.export_profiles import export_profiles


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _pwsh() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise click.ClickException("PowerShell (pwsh) is required for bundle commands")
    return shell


def _run_ps(script: Path, *args: str) -> None:
    cmd = [_pwsh(), "-File", str(script)] + list(args)
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        raise click.ClickException(f"Command failed with exit code {completed.returncode}: {' '.join(cmd)}")


@click.group()
@policy.require_role("operator", "maintainer")
@policy.enforce
def bundle() -> None:
    """Offline bundle helpers."""


@bundle.command()
@click.option("--canonical", type=click.Path(path_type=Path), default=Path("kg/canonical"))
def build(canonical: Path) -> None:
    """Build the offline bundle under dist/offline_bundle."""
    repo = _repo_root()
    script = repo / "scripts" / "build-offline-bundle.ps1"
    args = ["-CanonicalDir", str(canonical)] if canonical != Path("kg/canonical") else []
    _run_ps(script, *args)


@bundle.command()
@click.option("--path", type=click.Path(path_type=Path), default=Path("dist/offline_bundle"))
def verify(path: Path) -> None:
    """Verify bundle checksums."""
    script = path / "scripts" / "bundle-verify.ps1"
    if not script.exists():
        raise click.ClickException(f"Verification script not found under {script.parent}")
    _run_ps(script, "-Path", str(path))


@bundle.command()
@click.option("--path", type=click.Path(path_type=Path), default=Path("dist/offline_bundle"))
def smoke(path: Path) -> None:
    """Run first-run bootstrap smoke test."""
    script = path / "scripts" / "bundle-first-run.ps1"
    if not script.exists():
        raise click.ClickException(f"First-run script not found under {script.parent}")
    _run_ps(script, "-Path", str(path))


@bundle.command("export-profiles")
@click.option("--ttl", type=click.Path(path_type=Path), required=True, help="Source Turtle file")
@click.option("--out", type=click.Path(path_type=Path), default=Path("dist/exports"))
@click.option("--stem", type=str, default="dataset")
def export_profiles_cmd(ttl: Path, out: Path, stem: str) -> None:
    """Generate TTL/NT/gz profiles and manifest."""
    if not ttl.exists():
        raise click.ClickException(f"TTL source {ttl} not found")
    manifest = export_profiles(ttl, out, stem=stem)
    click.echo(f"Exported profiles to {out} ({len(manifest)} items)")
