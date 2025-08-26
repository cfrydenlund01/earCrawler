import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'kg' / 'scripts' / 'ci-roundtrip.ps1'
JENA_DIR = pathlib.Path('tools') / 'jena'
FUSEKI_DIR = pathlib.Path('tools') / 'fuseki'


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_ci_roundtrip_script_exists():
    assert SCRIPT.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_ci_roundtrip_runs_if_tools_present():
    if not (JENA_DIR.exists() and FUSEKI_DIR.exists()):
        pytest.skip("Jena or Fuseki tools missing")
    result = subprocess.run(["pwsh", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_snapshot_files_exist_after_ci():
    snap_dir = pathlib.Path('kg') / 'snapshots'
    assert snap_dir.exists()
    list(snap_dir.glob('*.srj'))  # should not raise
