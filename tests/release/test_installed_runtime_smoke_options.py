import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("require_pwsh")

ROOT = Path(__file__).resolve().parents[2]


def run_ps(script, *args, check=True):
    cmd = ["pwsh", "-File", str(ROOT / script)] + list(args)
    env_vars = dict(os.environ)
    return subprocess.run(cmd, cwd=ROOT, env=env_vars, check=check)


def test_require_full_baseline_requires_live_fuseki_flag():
    result = run_ps(
        "scripts/installed-runtime-smoke.ps1",
        "-RequireFullBaseline",
        check=False,
    )
    assert result.returncode != 0


def test_live_fuseki_requires_url_without_auto_provision():
    result = run_ps(
        "scripts/installed-runtime-smoke.ps1",
        "-UseLiveFuseki",
        check=False,
    )
    assert result.returncode != 0


def test_hermetic_bundle_requires_release_checksums():
    result = run_ps(
        "scripts/installed-runtime-smoke.ps1",
        "-UseHermeticWheelhouse",
        "-HermeticBundleZipPath",
        "dist/hermetic-artifacts.zip",
        check=False,
    )
    assert result.returncode != 0
