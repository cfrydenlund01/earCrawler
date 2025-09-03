import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def run_ps(script, *args, env=None):
    cmd = ["pwsh", "-File", str(ROOT / script)] + list(args)
    env_vars = dict(os.environ)
    if env:
        env_vars.update(env)
    subprocess.run(cmd, check=True, cwd=ROOT, env=env_vars)

def test_manifest_schema(tmp_path):
    env = dict(SOURCE_DATE_EPOCH="946684800")
    snap_dir = ROOT / "kg" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "dataset.nq").write_text("b .\na .\n", encoding="utf-8")
    (snap_dir / "sample.srj").write_text('{"b":1,"a":2}', encoding="utf-8")
    run_ps("kg/scripts/canonical-freeze.ps1", env=env)
    run_ps("scripts/make-canonical-zip.ps1", env=env)
    run_ps("scripts/make-manifest.ps1", env=env)
    manifest_path = ROOT / "kg" / "canonical" / "manifest.json"
    data = json.loads(manifest_path.read_text())
    assert isinstance(data.get("files"), list)
    for f in data["files"]:
        assert set(f.keys()) == {"path", "size", "sha256"}
        assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"])
        assert not str(f["path"]).startswith("\\")
        assert f["size"] > 0
