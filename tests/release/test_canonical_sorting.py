import json
import os
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_ps(script, *args, env=None):
    cmd = ["pwsh", "-File", str(ROOT / script)] + list(args)
    env_vars = dict(os.environ)
    if env:
        env_vars.update(env)
    subprocess.run(cmd, check=True, cwd=ROOT, env=env_vars)


def test_canonical_sorting(tmp_path):
    snap_dir = ROOT / "kg" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "dataset.nq").write_text("b .\na .\n", encoding="utf-8")
    (snap_dir / "sample.srj").write_text('{"b":1,"a":2}', encoding="utf-8")
    env = dict(SOURCE_DATE_EPOCH="946684800")
    run_ps("kg/scripts/canonical-freeze.ps1", env=env)
    # dataset.nq sorted
    lines = (ROOT / "kg" / "canonical" / "dataset.nq").read_text().splitlines()
    assert lines == sorted(lines)
    # JSON keys sorted
    srj_text = (ROOT / "kg" / "canonical" / "snapshots" / "sample.srj").read_text()
    assert srj_text.index("\"a\"") < srj_text.index("\"b\"")
    # ZIP timestamps
    run_ps("scripts/make-canonical-zip.ps1", "-Version", "test", env=env)
    zip_path = next((ROOT / "dist").glob("*.zip"))
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            assert info.date_time == (2000, 1, 1, 0, 0, 0)
