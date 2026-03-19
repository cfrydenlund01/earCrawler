import os
import subprocess
import hashlib
import json
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


def test_verify_records_installed_runtime_smoke_status(tmp_path):
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

    installed_runtime = tmp_path / "installed_runtime_smoke.json"
    installed_runtime.write_text(
        json.dumps(
            {
                "schema_version": "installed-runtime-smoke.v1",
                "overall_status": "passed",
                "install_mode": "hermetic_wheelhouse",
                "install_source": "release_bundle",
                "checks": [
                    {"name": "health_http_200", "passed": True},
                    {"name": "supported_api_smoke", "passed": True},
                    {"name": "install_source", "passed": True},
                    {"name": "runtime_contract_topology", "passed": True},
                    {
                        "name": "runtime_contract_declared_instance_count",
                        "passed": True,
                    },
                    {
                        "name": "runtime_contract_capability_registry_schema",
                        "passed": True,
                    },
                    {
                        "name": "runtime_contract_api_default_surface",
                        "passed": True,
                    },
                    {"name": "runtime_contract_api_search", "passed": True},
                    {"name": "runtime_contract_kg_expansion", "passed": True},
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    evidence = tmp_path / "release_validation_evidence.json"
    run_ps(
        "scripts/verify-release.ps1",
        "-ChecksumsPath",
        str(checksums),
        "-InstalledRuntimeSmokeReportPath",
        str(installed_runtime),
        "-EvidenceOutPath",
        str(evidence),
        env=env,
    )

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["installed_runtime_smoke"]["status"] == "passed"
    assert payload["installed_runtime_smoke"]["schema_version"] == "installed-runtime-smoke.v1"
    assert payload["installed_runtime_smoke"]["install_mode"] == "hermetic_wheelhouse"
    assert payload["installed_runtime_smoke"]["install_source"] == "release_bundle"
    assert payload["installed_runtime_smoke"]["hermetic_install_status"] == "passed"
    assert payload["installed_runtime_smoke"]["field_install_shape_status"] == "passed"


def test_verify_records_security_and_observability_evidence_status(tmp_path):
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

    security_summary = tmp_path / "security_scan_summary.json"
    security_summary.write_text(
        json.dumps(
            {
                "schema_version": "ci-security-baseline.v1",
                "overall_status": "passed",
                "reports": {
                    "pip_audit": {"status": "passed", "path": "dist/security/pip_audit.json"},
                    "bandit": {"status": "passed", "path": "dist/security/bandit.json"},
                    "secret_scan": {"status": "passed", "path": "dist/security/secret_scan.json"},
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    observability_probe = tmp_path / "api_probe.json"
    observability_probe.write_text(
        json.dumps(
            {
                "schema_version": "api-probe-report.v1",
                "overall_status": "passed",
                "health": {
                    "status_code": 200,
                    "readiness_pass": True,
                    "budget_ok": True,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    evidence = tmp_path / "release_validation_evidence.json"
    run_ps(
        "scripts/verify-release.ps1",
        "-ChecksumsPath",
        str(checksums),
        "-SecuritySummaryPath",
        str(security_summary),
        "-ObservabilityApiProbePath",
        str(observability_probe),
        "-EvidenceOutPath",
        str(evidence),
        env=env,
    )

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["security_baseline"]["status"] == "passed"
    assert payload["security_baseline"]["overall_status"] == "passed"
    assert payload["observability_api_probe"]["status"] == "passed"
    assert payload["observability_api_probe"]["health_status_code"] == 200
