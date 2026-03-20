import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("require_pwsh")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "bootstrap-verify.ps1"


def run_bootstrap(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["pwsh", "-File", str(SCRIPT)] + list(args)
    env = dict(os.environ)
    return subprocess.run(cmd, cwd=ROOT, env=env, check=check)


def test_bootstrap_verify_fails_when_project_venv_missing(tmp_path: Path) -> None:
    result = run_bootstrap(
        "-RootPath",
        str(tmp_path),
        "-SkipPyLauncherCheck",
        "-SkipJavaCheck",
        check=False,
    )
    assert result.returncode != 0


def test_bootstrap_verify_passes_with_venv_when_optional_checks_skipped(tmp_path: Path) -> None:
    run_bootstrap(
        "-RootPath",
        str(tmp_path),
        "-VenvPath",
        str(ROOT / ".venv"),
        "-SkipPyLauncherCheck",
        "-SkipJavaCheck",
    )
