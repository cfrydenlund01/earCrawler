from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build-offline-bundle.ps1"
VERIFY_SCRIPT = ROOT / "dist" / "offline_bundle" / "scripts" / "bundle-verify.ps1"

pytestmark = pytest.mark.usefixtures("require_pwsh")


def run_build(tmp_env: dict[str, str] | None = None) -> Path:
    subprocess.run(["pwsh", "-File", str(BUILD_SCRIPT)], check=True, cwd=ROOT, env=tmp_env)
    return ROOT / "dist" / "offline_bundle"


def test_manifest_sorted_and_verify(tmp_path):
    bundle = run_build(None)
    manifest_path = bundle / "manifest.json"
    data = json.loads(manifest_path.read_text())
    paths = [entry["path"] for entry in data["files"]]
    assert paths == sorted(paths)
    assert all(len(entry["sha256"]) == 64 for entry in data["files"])

    checksums = (bundle / "checksums.sha256").read_text().splitlines()
    sorted_lines = sorted(line for line in checksums if line.strip())
    assert checksums == sorted_lines

    subprocess.run(["pwsh", "-File", str(bundle / "scripts" / "bundle-verify.ps1"), "-Path", str(bundle)], check=True, cwd=ROOT)

    # determinism: rebuild and ensure manifest unchanged
    manifest_copy = manifest_path.read_text()
    bundle = run_build(None)
    assert manifest_path.read_text() == manifest_copy


