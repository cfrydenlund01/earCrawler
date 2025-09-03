import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_ps(script, *args, env=None, check=True):
    cmd = ["pwsh", "-File", str(ROOT / script)] + list(args)
    env_vars = dict(os.environ)
    if env:
        env_vars.update(env)
    return subprocess.run(cmd, cwd=ROOT, env=env_vars, check=check)


def test_verify_detects_tamper(tmp_path):
    env = dict(SOURCE_DATE_EPOCH="946684800")
    run_ps("kg/scripts/canonical-freeze.ps1", env=env)
    # add simple file
    target = ROOT / "kg" / "canonical" / "foo.txt"
    target.write_text("hello", encoding="utf-8")
    run_ps("scripts/make-manifest.ps1", env=env)
    # verification passes
    run_ps("scripts/verify-release.ps1", env=env)
    # tamper
    target.write_text("evil", encoding="utf-8")
    res = run_ps("scripts/verify-release.ps1", env=env, check=False)
    assert res.returncode != 0
