import subprocess
import sys
from pathlib import Path
import os

import pytest

LOCK_CONTENT = """click==8.2.1 \\
    --hash=sha256:27c491cc05d968d271d5a1db13e3b5a184636d9d930f148c50b038f0d0646202 \\
    --hash=sha256:61a3265b914e850b85317d0b3109c7f8cd35a670f963866005d6ef1d5175a12b
colorama==0.4.6 \\
    --hash=sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6
"""


def _pip(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / "pip"


def test_hash_locked_install(tmp_path):
    good = tmp_path / "good.txt"
    good.write_text(LOCK_CONTENT)
    bad = tmp_path / "bad.txt"
    bad.write_text("click==8.2.1\n")
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("click==8.2.1 \\\n     --hash=sha256:" + "0" * 64 + "\n")
    venv = tmp_path / "venv"
    subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    pip = _pip(venv)

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_call([str(pip), "install", "--require-hashes", "-r", str(bad)])
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_call([str(pip), "install", "--require-hashes", "-r", str(wrong)])

    subprocess.check_call([str(pip), "install", "--require-hashes", "-r", str(good)])

