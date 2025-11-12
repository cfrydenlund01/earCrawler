import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("kg/scripts/ci-incremental.ps1")
MANIFEST = Path("kg/.kgstate/manifest.json")
STATUS = Path("kg/reports/incremental-status.json")
NOOP = Path("kg/reports/incremental-noop.txt")
SNAPSHOT = Path("kg/snapshots/smoke.srj")
INC_TOUCH = Path("kg/testdata/inc_touch.ttl")

run = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


@pytest.fixture(autouse=True)
def cleanup_inc_touch():
    if INC_TOUCH.exists():
        INC_TOUCH.unlink()
    yield
    if INC_TOUCH.exists():
        INC_TOUCH.unlink()


def _run_script():
    env = os.environ.copy()
    env["INCREMENTAL_SCAN_ONLY"] = "1"
    exe = _powershell_executable()
    subprocess.run([exe, "-File", str(SCRIPT)], check=True, env=env)
    return json.loads(STATUS.read_text())


def _powershell_executable():
    for candidate in ("pwsh", "pwsh.exe", "powershell", "powershell.exe"):
        path = shutil.which(candidate)
        if path:
            return path
    pytest.fail(
        "No PowerShell executable was found on PATH. Install PowerShell 7 and "
        "retry the incremental CI tests.",
        pytrace=False,
    )


@run
def test_incremental_first_run_marks_changed():
    if MANIFEST.exists():
        MANIFEST.unlink()
    status = _run_script()
    assert status["changed"] is True
    assert STATUS.exists()


@run
def test_incremental_second_run_noop():
    before = SNAPSHOT.stat().st_mtime
    status = _run_script()
    assert status["changed"] is False
    assert NOOP.exists()
    after = SNAPSHOT.stat().st_mtime
    assert before == after


@run
def test_incremental_detects_touch(tmp_path):
    INC_TOUCH.write_text("test")
    status = _run_script()
    assert status["changed"] is True
    assert "kg/testdata/inc_touch.ttl" in status["paths"]
