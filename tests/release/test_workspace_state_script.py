import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("require_pwsh")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "workspace-state.ps1"


def run_workspace_state(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["pwsh", "-File", str(SCRIPT)] + list(args)
    return subprocess.run(cmd, cwd=ROOT, env=dict(os.environ), check=check)


def test_verify_fails_when_ghost_workspace_residue_exists(tmp_path: Path) -> None:
    ghost = tmp_path / "earCrawler" / "agent"
    ghost.mkdir(parents=True, exist_ok=True)
    (ghost / "cache.bin").write_text("x", encoding="utf-8")

    result = run_workspace_state(
        "-RootPath",
        str(tmp_path),
        "-Mode",
        "verify",
        "-SkipGit",
        check=False,
    )
    assert result.returncode != 0


def test_clean_removes_ghost_and_disposable_but_keeps_dist_by_default(tmp_path: Path) -> None:
    ghost = tmp_path / "tests" / "models"
    ghost.mkdir(parents=True, exist_ok=True)
    (ghost / "cache.bin").write_text("x", encoding="utf-8")
    disposable = tmp_path / ".pytest_tmp123"
    disposable.mkdir(parents=True, exist_ok=True)
    venv_dir = tmp_path / ".venv_local"
    venv_dir.mkdir(parents=True, exist_ok=True)
    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    run_workspace_state(
        "-RootPath",
        str(tmp_path),
        "-Mode",
        "clean",
        "-SkipGit",
    )

    assert not ghost.exists()
    assert not disposable.exists()
    assert not build_dir.exists()
    assert dist_dir.exists()
    assert venv_dir.exists()


def test_clean_dist_requires_explicit_flag(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "artifact.txt").write_text("evidence", encoding="utf-8")

    run_workspace_state(
        "-RootPath",
        str(tmp_path),
        "-Mode",
        "clean",
        "-CleanDist",
        "-SkipGit",
    )
    assert not dist_dir.exists()


def test_clean_venvs_requires_explicit_flag(tmp_path: Path) -> None:
    venv_dir = tmp_path / ".venv_local"
    venv_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "python.exe").write_text("venv", encoding="utf-8")

    run_workspace_state(
        "-RootPath",
        str(tmp_path),
        "-Mode",
        "clean",
        "-CleanVenvs",
        "-SkipGit",
    )
    assert not venv_dir.exists()


def test_clean_keeps_tracked_ghost_named_path(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for tracked-path verification")

    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
    )

    tracked_path = tmp_path / "tests" / "models"
    tracked_path.mkdir(parents=True, exist_ok=True)
    tracked_file = tracked_path / "kept.txt"
    tracked_file.write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "add", str(tracked_file.relative_to(tmp_path))], cwd=tmp_path, check=True)

    run_workspace_state(
        "-RootPath",
        str(tmp_path),
        "-Mode",
        "clean",
    )

    assert tracked_path.exists()
    assert tracked_file.exists()
