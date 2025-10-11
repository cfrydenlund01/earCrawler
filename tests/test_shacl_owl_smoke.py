"""Run SHACL validation and OWL smoke checks via Apache Jena tools.

These tests require PowerShell and a Java runtime. The Apache Jena and
Fuseki distributions are downloaded on demand. Execution is limited to
Windows environments.
"""

import json
import os
import pathlib
import subprocess
import sys
import shutil

import pytest

from .java_utils import JAVA_VERSION_OK

SCRIPT = pathlib.Path('kg/scripts/ci-shacl-owl.ps1')
JENA_DIR = pathlib.Path('tools') / 'jena'
FUSEKI_DIR = pathlib.Path('tools') / 'fuseki'
REPORTS_DIR = pathlib.Path('kg') / 'reports'

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

if shutil.which("pwsh") is None:
    pytest.fail(
        "PowerShell 7 (pwsh) is required to run the SHACL/OWL smoke tests. "
        "Install pwsh and ensure it is on the PATH.",
        pytrace=False,
    )

if not JAVA_VERSION_OK:
    pytest.fail(
        "Java 17 or newer is required to run the SHACL/OWL smoke tests. Update "
        "the installed Java runtime and try again.",
        pytrace=False,
    )


def test_ci_shacl_owl_script_exists():
    assert SCRIPT.exists()


def test_shacl_report_artifacts_when_tools_present():
    if not (JENA_DIR.exists() and FUSEKI_DIR.exists()):
        pytest.fail(
            "The Apache Jena and Fuseki tools must be downloaded before running "
            "the SHACL/OWL smoke tests.",
            pytrace=False,
        )
    if REPORTS_DIR.exists():
        shutil.rmtree(REPORTS_DIR)
    env = {
        **os.environ,
        "JENA_HOME": str(JENA_DIR),
        "FUSEKI_HOME": str(FUSEKI_DIR),
    }
    result = subprocess.run(
        ["pwsh", str(SCRIPT)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stdout + result.stderr
    conforms_path = REPORTS_DIR / "shacl-conforms.txt"
    assert conforms_path.exists()
    assert conforms_path.read_text().strip() == "true"
    owl_json = REPORTS_DIR / "owl-smoke.json"
    assert owl_json.exists()
    data = json.loads(owl_json.read_text())
    assert len(data) == 3
    assert all(item["passed"] for item in data)
