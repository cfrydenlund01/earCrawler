from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("require_pwsh")

ROOT = Path(__file__).resolve().parents[2]


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_ps_command(command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["pwsh", "-Command", command]
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=dict(os.environ),
        check=check,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_write_release_stage_manifest_writes_deduped_hash_entries(tmp_path: Path) -> None:
    evidence_a = tmp_path / "a.txt"
    evidence_b = tmp_path / "b.txt"
    evidence_a.write_text("alpha", encoding="utf-8")
    evidence_b.write_text("bravo", encoding="utf-8")
    out = tmp_path / "manifest.json"

    script = ROOT / "scripts" / "write-release-stage-manifest.ps1"
    cmd = (
        f"& {_ps_quote(str(script))} "
        f"-Stage validation "
        f"-OutPath {_ps_quote(str(out))} "
        f"-Tag v9.9.9 "
        f"-EvidenceFiles @({_ps_quote(str(evidence_a))}, {_ps_quote(str(evidence_b))}, {_ps_quote(str(evidence_a))})"
    )
    _run_ps_command(cmd)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "release-promotion-stage.v1"
    assert payload["stage"] == "validation"
    assert payload["git_tag"] == "v9.9.9"
    assert payload["evidence_file_count"] == 2

    entries = payload["evidence_files"]
    assert len(entries) == 2
    hashes = {entry["sha256"] for entry in entries}
    assert _sha256(evidence_a) in hashes
    assert _sha256(evidence_b) in hashes


def test_write_release_stage_manifest_fails_when_evidence_file_missing(tmp_path: Path) -> None:
    out = tmp_path / "manifest.json"
    script = ROOT / "scripts" / "write-release-stage-manifest.ps1"
    missing = tmp_path / "missing.txt"
    cmd = (
        f"& {_ps_quote(str(script))} "
        f"-Stage build "
        f"-OutPath {_ps_quote(str(out))} "
        f"-EvidenceFiles @({_ps_quote(str(missing))})"
    )
    result = _run_ps_command(cmd, check=False)
    assert result.returncode != 0
