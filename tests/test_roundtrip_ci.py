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
from .tooling import require_jena_and_fuseki

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1] / "kg" / "scripts" / "ci-roundtrip.ps1"
)
MISSING_TOOLS_MSG = (
    "The Apache Jena and Fuseki tools must be downloaded before running "
    "the KG round-trip tests."
)

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

if shutil.which("pwsh") is None:
    pytest.fail(
        "PowerShell 7 (pwsh) is required to run the KG round-trip tests. "
        "Install pwsh and ensure it is on the PATH.",
        pytrace=False,
    )

if shutil.which("javac") is None:
    pytest.fail(
        "A Java 17+ JDK with the javac compiler is required to run the KG "
        "round-trip tests. Install an appropriate JDK and rerun.",
        pytrace=False,
    )

if not JAVA_VERSION_OK:
    pytest.fail(
        "Java 17 or newer is required to run the KG round-trip tests. Update "
        "the installed Java runtime and try again.",
        pytrace=False,
    )


def test_ci_roundtrip_script_exists():
    assert SCRIPT.exists()


def test_ci_roundtrip_runs_if_tools_present():
    jena_dir, fuseki_dir = require_jena_and_fuseki(MISSING_TOOLS_MSG)
    env = {
        **os.environ,
        "JENA_HOME": str(jena_dir),
        "FUSEKI_HOME": str(fuseki_dir),
    }
    result = subprocess.run(
        ["pwsh", str(SCRIPT)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_snapshot_files_exist_after_ci():
    snap_dir = pathlib.Path("kg") / "snapshots"
    assert snap_dir.exists()
    list(snap_dir.glob("*.srj"))  # should not raise
