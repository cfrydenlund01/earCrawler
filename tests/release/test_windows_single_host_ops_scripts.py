import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("require_pwsh")

ROOT = Path(__file__).resolve().parents[2]


def run_ps(script, *args, env=None, check=True):
    cmd = ["pwsh", "-File", str(ROOT / script)] + [str(arg) for arg in args]
    env_vars = dict(os.environ)
    if env:
        env_vars.update(env)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=env_vars,
        check=check,
        capture_output=True,
        text=True,
    )


def test_single_host_service_script_install_dry_run(tmp_path):
    result = run_ps(
        "scripts/ops/windows-single-host-service.ps1",
        "-Action",
        "install",
        "-RuntimeRoot",
        str(tmp_path / "runtime"),
        "-WorkspaceRoot",
        str(tmp_path / "workspace"),
        "-LogRoot",
        str(tmp_path / "logs"),
        "-NssmPath",
        str(tmp_path / "nssm.exe"),
        "-DryRun",
    )

    stdout = result.stdout.lower()
    assert "support contract" in stdout
    assert "single" in stdout
    assert "dry-run" in stdout
    assert "nssm" in stdout


def test_backup_and_restore_drill_scripts(tmp_path):
    program_data = tmp_path / "ProgramData" / "EarCrawler"
    runtime_root = tmp_path / "runtime"
    backup_root = program_data / "backups"

    for rel in ("config", "logs", "workspace", "audit", "spool"):
        target = program_data / rel
        target.mkdir(parents=True, exist_ok=True)
        (target / "sample.txt").write_text(f"{rel}-data", encoding="utf-8")

    run_ps(
        "scripts/ops/windows-single-host-backup.ps1",
        "-ProgramDataRoot",
        str(program_data),
        "-RuntimeRoot",
        str(runtime_root),
        "-BackupRoot",
        str(backup_root),
        "-BackupId",
        "snapshot-test",
        "-SkipServiceControl",
    )

    snapshot = backup_root / "snapshot-test"
    manifest_path = snapshot / "snapshot_manifest.json"
    checksums_path = snapshot / "checksums.sha256"
    assert manifest_path.exists()
    assert checksums_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "windows-single-host-backup.v1"
    assert manifest["backup_id"] == "snapshot-test"
    assert "config" in manifest["copied_paths"]
    assert len(manifest["files"]) > 0

    drill_root = tmp_path / "drill"
    run_ps(
        "scripts/ops/windows-single-host-restore-drill.ps1",
        "-SnapshotPath",
        str(snapshot),
        "-DrillRoot",
        str(drill_root),
    )

    report_path = drill_root / "restore_drill_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "windows-single-host-restore-drill.v1"
    assert report["status"] == "pass"
    assert (drill_root / "restore_preview" / "config").exists()


def test_recurring_dr_evidence_runner_produces_report_and_index(tmp_path):
    program_data = tmp_path / "ProgramData" / "EarCrawler"
    runtime_root = tmp_path / "runtime"
    api_backup_root = program_data / "backups"
    fuseki_program_data = program_data / "fuseki"
    fuseki_backup_root = program_data / "backups" / "fuseki"
    evidence_root = api_backup_root / "recurring-evidence"
    fuseki_home = tmp_path / "Apache" / "Jena-Fuseki-5.3.0"

    for rel in ("config", "logs", "workspace", "audit", "spool"):
        target = program_data / rel
        target.mkdir(parents=True, exist_ok=True)
        (target / "sample.txt").write_text(f"{rel}-data", encoding="utf-8")

    for rel in ("config", "databases", "logs"):
        target = fuseki_program_data / rel
        target.mkdir(parents=True, exist_ok=True)
        (target / "sample.txt").write_text(f"fuseki-{rel}-data", encoding="utf-8")

    run_ps(
        "scripts/ops/windows-recurring-dr-evidence.ps1",
        "-RunId",
        "recurring-test",
        "-ProgramDataRoot",
        str(program_data),
        "-RuntimeRoot",
        str(runtime_root),
        "-ApiBackupRoot",
        str(api_backup_root),
        "-FusekiProgramDataRoot",
        str(fuseki_program_data),
        "-FusekiHome",
        str(fuseki_home),
        "-FusekiBackupRoot",
        str(fuseki_backup_root),
        "-EvidenceRoot",
        str(evidence_root),
        "-SkipServiceControl",
    )

    report_path = evidence_root / "dr-evidence-run-recurring-test.json"
    index_path = evidence_root / "dr-evidence-index.json"
    assert report_path.exists()
    assert index_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "windows-recurring-dr-evidence.v1"
    assert report["run_id"] == "recurring-test"
    assert report["overall_status"] == "pass"
    assert report["api"]["status"] == "pass"
    assert report["fuseki"]["status"] == "pass"

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["schema_version"] == "windows-recurring-dr-evidence-index.v1"
    assert index["runs"][0]["run_id"] == "recurring-test"
