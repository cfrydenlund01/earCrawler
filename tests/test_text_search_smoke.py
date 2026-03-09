"""Smoke test for text-backed entity search against real Fuseki."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from .java_utils import JAVA_VERSION_OK
from .tooling import require_jena_and_fuseki

SCRIPT = pathlib.Path("kg/scripts/ci-text-search-smoke.ps1")
REPORT_PATH = pathlib.Path("kg/reports/text-search-smoke.json")
MISSING_TOOLS_MSG = (
    "The Apache Jena and Fuseki tools must be downloaded before running "
    "the text search smoke test."
)

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

if shutil.which("pwsh") is None:
    pytest.skip(
        "PowerShell 7 (pwsh) is required to run the text search smoke test. "
        "Install pwsh and ensure it is on the PATH.",
        allow_module_level=True,
    )

if not JAVA_VERSION_OK:
    pytest.skip(
        "Java 17 or newer is required to run the text search smoke test. Update "
        "the installed Java runtime and try again.",
        allow_module_level=True,
    )


def test_text_search_script_exists() -> None:
    assert SCRIPT.exists()


def test_text_search_smoke_when_tools_present() -> None:
    jena_dir, fuseki_dir = require_jena_and_fuseki(MISSING_TOOLS_MSG)
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    env = {
        **os.environ,
        "JENA_HOME": str(jena_dir),
        "FUSEKI_HOME": str(fuseki_dir),
    }
    result = subprocess.run(
        ["pwsh", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert REPORT_PATH.exists()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report["passed"] is True
    payload = report["payload"]
    assert payload["total"] >= 1
    ids = {row["id"] for row in payload["results"]}
    assert "urn:ear:entity:smoke-1" in ids
