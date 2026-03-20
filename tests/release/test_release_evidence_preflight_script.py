import hashlib
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


def make_release_root(tmp_path: Path):
    release_root = tmp_path / "release"
    release_root.mkdir(parents=True, exist_ok=True)
    artifact = release_root / "artifact.txt"
    artifact.write_text("release-ok", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksums = release_root / "checksums.sha256"
    checksums.write_text(f"{digest}  artifact.txt\n", encoding="utf-8")
    (release_root / "checksums.sha256.sig").write_text("test-signature", encoding="utf-8")
    return release_root, artifact, checksums


def test_release_evidence_preflight_passes_for_controlled_release_root(tmp_path):
    _, _, checksums = make_release_root(tmp_path)
    run_ps("scripts/release-evidence-preflight.ps1", "-ChecksumsPath", str(checksums))


def test_release_evidence_preflight_fails_on_checksum_tamper(tmp_path):
    _, artifact, checksums = make_release_root(tmp_path)
    artifact.write_text("tampered", encoding="utf-8")

    result = run_ps(
        "scripts/release-evidence-preflight.ps1",
        "-ChecksumsPath",
        str(checksums),
        check=False,
    )
    assert result.returncode != 0


def test_release_evidence_preflight_fails_when_signature_is_missing(tmp_path):
    release_root, _, checksums = make_release_root(tmp_path)
    (release_root / "checksums.sha256.sig").unlink()

    result = run_ps(
        "scripts/release-evidence-preflight.ps1",
        "-ChecksumsPath",
        str(checksums),
        check=False,
    )
    assert result.returncode != 0


def test_release_evidence_preflight_fails_with_untracked_top_level_artifact(tmp_path):
    release_root, _, checksums = make_release_root(tmp_path)
    (release_root / "stale.zip").write_text("leftover", encoding="utf-8")

    result = run_ps(
        "scripts/release-evidence-preflight.ps1",
        "-ChecksumsPath",
        str(checksums),
        check=False,
    )
    assert result.returncode != 0


def test_release_evidence_preflight_fails_when_checksums_missing_with_release_outputs(tmp_path):
    release_root = tmp_path / "dist"
    release_root.mkdir(parents=True, exist_ok=True)
    (release_root / "earcrawler-0.0.1-py3-none-any.whl").write_text("wheel", encoding="utf-8")

    result = run_ps(
        "scripts/release-evidence-preflight.ps1",
        "-ChecksumsPath",
        str(release_root / "checksums.sha256"),
        check=False,
    )
    assert result.returncode != 0

