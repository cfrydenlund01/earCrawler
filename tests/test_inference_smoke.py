"""Smoke tests for inference scripts using Apache Jena and Fuseki.

These tests require PowerShell, a Java runtime, and network access to
download the tools on demand. They are only executed on Windows systems.
"""

import json
import os
import pathlib
import subprocess
import sys
import shutil

import pytest

from .java_utils import JAVA_VERSION_OK

SCRIPT = pathlib.Path('kg/scripts/ci-inference-smoke.ps1')
JENA_DIR = pathlib.Path('tools') / 'jena'
FUSEKI_DIR = pathlib.Path('tools') / 'fuseki'
REPORTS_DIR = pathlib.Path('kg') / 'reports'

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

if shutil.which("pwsh") is None:
    pytest.fail(
        "PowerShell 7 (pwsh) is required to run the inference smoke tests. "
        "Install pwsh and ensure it is on the PATH.",
        pytrace=False,
    )

if not JAVA_VERSION_OK:
    pytest.fail(
        "Java 17 or newer is required to run the inference smoke tests. Update "
        "the installed Java runtime and try again.",
        pytrace=False,
    )


def test_inference_script_exists():
    assert SCRIPT.exists()


def test_inference_rdfs_smoke_when_tools_present():
    if not (JENA_DIR.exists() and FUSEKI_DIR.exists()):
        pytest.fail(
            "The Apache Jena and Fuseki tools must be downloaded before running "
            "the inference smoke tests.",
            pytrace=False,
        )
    if REPORTS_DIR.exists():
        shutil.rmtree(REPORTS_DIR)
    env = {
        **os.environ,
        "JENA_HOME": str(JENA_DIR),
        "FUSEKI_HOME": str(FUSEKI_DIR),
    }
    result = subprocess.run([
        "pwsh",
        str(SCRIPT),
        "-Mode",
        "rdfs",
    ], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    json_path = REPORTS_DIR / "inference-rdfs.json"
    select_path = REPORTS_DIR / "inference-rdfs-select.srj"
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert all(item["passed"] for item in data)
    assert select_path.exists()
    assert select_path.stat().st_size > 0


def test_inference_owlmini_smoke_when_tools_present():
    if not (JENA_DIR.exists() and FUSEKI_DIR.exists()):
        pytest.fail(
            "The Apache Jena and Fuseki tools must be downloaded before running "
            "the inference smoke tests.",
            pytrace=False,
        )
    env = {
        **os.environ,
        "JENA_HOME": str(JENA_DIR),
        "FUSEKI_HOME": str(FUSEKI_DIR),
    }
    result = subprocess.run([
        "pwsh",
        str(SCRIPT),
        "-Mode",
        "owlmini",
    ], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    json_path = REPORTS_DIR / "inference-owlmini.json"
    select_path = REPORTS_DIR / "inference-owlmini-select.srj"
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert all(item["passed"] for item in data)
    assert select_path.exists()
    assert select_path.stat().st_size > 0
