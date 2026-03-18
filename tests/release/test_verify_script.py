import os
import subprocess
import hashlib
from pathlib import Path
import pytest

pytestmark = pytest.mark.usefixtures("require_pwsh")

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


def test_verify_detects_dist_checksum_tamper(tmp_path):
    env = dict(SOURCE_DATE_EPOCH="946684800")
    run_ps("kg/scripts/canonical-freeze.ps1", env=env)
    run_ps("scripts/make-manifest.ps1", env=env)

    release_dir = tmp_path / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    artifact = release_dir / "artifact.txt"
    artifact.write_text("release-ok", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksums = release_dir / "checksums.sha256"
    checksums.write_text(f"{digest}  artifact.txt\n", encoding="utf-8")
    evidence = tmp_path / "release_validation_evidence.json"

    run_ps(
        "scripts/verify-release.ps1",
        "-ChecksumsPath",
        str(checksums),
        "-EvidenceOutPath",
        str(evidence),
        env=env,
    )
    artifact.write_text("tampered", encoding="utf-8")
    res = run_ps(
        "scripts/verify-release.ps1",
        "-ChecksumsPath",
        str(checksums),
        "-EvidenceOutPath",
        str(evidence),
        env=env,
        check=False,
    )
    assert res.returncode != 0


def test_verify_fails_when_placeholder_artifacts_are_in_release_outputs(tmp_path):
    env = dict(SOURCE_DATE_EPOCH="946684800")
    run_ps("kg/scripts/canonical-freeze.ps1", env=env)
    run_ps("scripts/make-manifest.ps1", env=env)

    release_dir = tmp_path / "dist"
    release_dir.mkdir(parents=True, exist_ok=True)
    artifact = release_dir / "artifact.txt"
    artifact.write_text("release-ok", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksums = release_dir / "checksums.sha256"
    checksums.write_text(f"{digest}  artifact.txt\n", encoding="utf-8")

    # Simulate offline bundle output that still carries a placeholder artifact.
    placeholder = release_dir / "offline_bundle" / "manifest.sig.PLACEHOLDER.txt"
    placeholder.parent.mkdir(parents=True, exist_ok=True)
    placeholder.write_text("replace before release", encoding="utf-8")

    res = run_ps(
        "scripts/verify-release.ps1",
        "-ChecksumsPath",
        str(checksums),
        "-EvidenceOutPath",
        str(tmp_path / "release_validation_evidence.json"),
        env=env,
        check=False,
    )
    assert res.returncode != 0


def test_verify_requires_complete_evidence_for_release_publication(tmp_path):
    env = dict(SOURCE_DATE_EPOCH="946684800")
    run_ps("kg/scripts/canonical-freeze.ps1", env=env)
    run_ps("scripts/make-manifest.ps1", env=env)

    release_dir = tmp_path / "dist"
    release_dir.mkdir(parents=True, exist_ok=True)
    artifact = release_dir / "artifact.txt"
    artifact.write_text("release-ok", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksums = release_dir / "checksums.sha256"
    checksums.write_text(f"{digest}  artifact.txt\n", encoding="utf-8")

    res = run_ps(
        "scripts/verify-release.ps1",
        "-ChecksumsPath",
        str(checksums),
        "-EvidenceOutPath",
        str(tmp_path / "release_validation_evidence.json"),
        "-ApiSmokeReportPath",
        str(tmp_path / "missing_api_smoke.json"),
        "-OptionalRuntimeSmokeReportPath",
        str(tmp_path / "missing_optional_runtime_smoke.json"),
        "-RequireCompleteEvidence",
        env=env,
        check=False,
    )
    assert res.returncode != 0
