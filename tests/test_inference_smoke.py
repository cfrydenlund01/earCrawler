import json
import pathlib
import subprocess
import sys
import shutil

import pytest

SCRIPT = pathlib.Path('kg/scripts/ci-inference-smoke.ps1')
JENA_DIR = pathlib.Path('tools') / 'jena'
FUSEKI_DIR = pathlib.Path('tools') / 'fuseki'
REPORTS_DIR = pathlib.Path('kg') / 'reports'


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_inference_script_exists():
    assert SCRIPT.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_inference_rdfs_smoke_when_tools_present():
    if not (JENA_DIR.exists() and FUSEKI_DIR.exists()):
        pytest.skip("Jena or Fuseki tools missing")
    if REPORTS_DIR.exists():
        shutil.rmtree(REPORTS_DIR)
    result = subprocess.run([
        "pwsh",
        str(SCRIPT),
        "-Mode",
        "rdfs",
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    json_path = REPORTS_DIR / "inference-rdfs.json"
    select_path = REPORTS_DIR / "inference-rdfs-select.srj"
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert all(item["passed"] for item in data)
    assert select_path.exists()
    assert select_path.stat().st_size > 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_inference_owlmini_smoke_when_tools_present():
    if not (JENA_DIR.exists() and FUSEKI_DIR.exists()):
        pytest.skip("Jena or Fuseki tools missing")
    result = subprocess.run([
        "pwsh",
        str(SCRIPT),
        "-Mode",
        "owlmini",
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    json_path = REPORTS_DIR / "inference-owlmini.json"
    select_path = REPORTS_DIR / "inference-owlmini-select.srj"
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert all(item["passed"] for item in data)
    assert select_path.exists()
    assert select_path.stat().st_size > 0
