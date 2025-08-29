"""Round-trip tests for KG build pipeline using Apache Jena tools.

These tests execute PowerShell scripts that require the Java Development Kit
and are only run on Windows platforms.
"""

import os
import pathlib
import subprocess
import sys
import shutil

import pytest

from .java_utils import JAVA_VERSION_OK

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / 'kg'
    / 'scripts'
    / 'ci-roundtrip.ps1'
)
JENA_DIR = pathlib.Path('tools') / 'jena'
FUSEKI_DIR = pathlib.Path('tools') / 'fuseki'

if (
    shutil.which("pwsh") is None
    or shutil.which("javac") is None
    or not JAVA_VERSION_OK
):
    pytest.skip(
        "PowerShell 7 and a JDK 17+ with javac are required",
        allow_module_level=True,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_ci_roundtrip_script_exists():
    assert SCRIPT.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_ci_roundtrip_runs_if_tools_present():
    if not (JENA_DIR.exists() and FUSEKI_DIR.exists()):
        pytest.skip("Jena or Fuseki tools missing")
    env = {
        **os.environ,
        "JENA_HOME": str(JENA_DIR),
        "FUSEKI_HOME": str(FUSEKI_DIR),
    }
    result = subprocess.run(
        ["pwsh", str(SCRIPT)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_snapshot_files_exist_after_ci():
    snap_dir = pathlib.Path('kg') / 'snapshots'
    assert snap_dir.exists()
    list(snap_dir.glob('*.srj'))  # should not raise
