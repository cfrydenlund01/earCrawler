from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from earCrawler import __version__


def test_python_module_version():
    out = subprocess.check_output([sys.executable, "-m", "earCrawler.cli", "--version"], text=True)
    assert __version__ in out.strip()


def test_python_module_diagnose():
    out = subprocess.check_output([sys.executable, "-m", "earCrawler.cli", "diagnose"], text=True)
    data = json.loads(out)
    assert data["earCrawler"] == __version__


@pytest.mark.skipif(sys.platform != "win32", reason="EXE only on Windows")
def test_exe_smoke():
    exe = next(Path("dist").glob("earctl-*-win64.exe"), None)
    if exe is None:
        pytest.skip("exe not built")
    out = subprocess.check_output([str(exe), "--version"], text=True)
    assert __version__ in out.strip()
    out2 = subprocess.check_output([str(exe), "diagnose"], text=True)
    data = json.loads(out2)
    assert data["earCrawler"] == __version__
