from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli.__main__ import cli
from earCrawler.rag.offline_snapshot_manifest import MANIFEST_VERSION, compute_sha256_hex


GOOD_FIXTURE = Path("tests/fixtures/ecfr_snapshot_min.jsonl")
BAD_FIXTURE = Path("tests/fixtures/ecfr_snapshot_bad_null_text.jsonl")


def _write_manifest(path: Path, *, payload_name: str, payload_path: Path) -> Path:
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "snapshot_id": "cli-test-snapshot",
        "created_at": "2026-02-10T00:00:00Z",
        "source": {
            "owner": "tests",
            "upstream": "unit-test",
            "approved_by": "tests",
            "approved_at": "2026-02-10T00:00:00Z",
        },
        "scope": {
            "titles": ["15"],
            "parts": [],
        },
        "payload": {
            "path": payload_name,
            "size_bytes": payload_path.stat().st_size,
            "sha256": compute_sha256_hex(payload_path),
        },
    }
    manifest_path = path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path


def test_rag_index_validate_snapshot_cli_passes(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(GOOD_FIXTURE.read_bytes())
    manifest = _write_manifest(tmp_path, payload_name="snapshot.jsonl", payload_path=payload)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "rag-index",
            "validate-snapshot",
            "--snapshot",
            str(payload),
            "--snapshot-manifest",
            str(manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Snapshot valid:" in result.output
    assert "sections=2" in result.output
    assert "titles=1" in result.output


def test_rag_index_validate_snapshot_cli_fails_with_line(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(BAD_FIXTURE.read_bytes())
    manifest = _write_manifest(tmp_path, payload_name="snapshot.jsonl", payload_path=payload)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "rag-index",
            "validate-snapshot",
            "--snapshot",
            str(payload),
            "--snapshot-manifest",
            str(manifest),
        ],
    )
    assert result.exit_code != 0
    assert "snapshot.jsonl:1 unexpected null text block in 'text'" in result.output

