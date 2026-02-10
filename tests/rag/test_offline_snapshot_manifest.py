from __future__ import annotations

import json
from pathlib import Path

import pytest

from earCrawler.rag.offline_snapshot_manifest import (
    MANIFEST_VERSION,
    compute_sha256_hex,
    require_offline_snapshot_manifest,
    validate_offline_snapshot,
    validate_snapshot_payload,
)


FIXTURE = Path("tests/fixtures/ecfr_snapshot_min.jsonl")
BAD_NULL_TEXT_FIXTURE = Path("tests/fixtures/ecfr_snapshot_bad_null_text.jsonl")
BAD_DUPLICATE_FIXTURE = Path("tests/fixtures/ecfr_snapshot_bad_duplicate.jsonl")


def _write_manifest(
    dir_path: Path,
    *,
    payload_name: str,
    sha256_hex: str,
    size_bytes: int,
    parts: list[str] | None = None,
) -> Path:
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "snapshot_id": "test-snapshot",
        "created_at": "2026-02-10T00:00:00Z",
        "source": {
            "owner": "tests",
            "upstream": "unit-test",
            "approved_by": "tests",
            "approved_at": "2026-02-10T00:00:00Z",
        },
        "scope": {"titles": ["15"], "parts": parts if parts is not None else []},
        "payload": {"path": payload_name, "size_bytes": size_bytes, "sha256": sha256_hex},
    }
    path = dir_path / "manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def test_validate_snapshot_payload_accepts_fixture() -> None:
    validate_snapshot_payload(FIXTURE)


def test_require_manifest_missing_fails(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(ValueError, match="manifest missing"):
        require_offline_snapshot_manifest(payload)


def test_require_manifest_hash_mismatch_fails(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(FIXTURE.read_bytes())
    _write_manifest(tmp_path, payload_name="snapshot.jsonl", sha256_hex="0" * 64, size_bytes=payload.stat().st_size)
    with pytest.raises(ValueError, match="payload\\.sha256 mismatch"):
        require_offline_snapshot_manifest(payload)


def test_require_manifest_ok(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(FIXTURE.read_bytes())
    sha256_hex = compute_sha256_hex(payload)
    _write_manifest(tmp_path, payload_name="snapshot.jsonl", sha256_hex=sha256_hex, size_bytes=payload.stat().st_size)
    manifest = require_offline_snapshot_manifest(payload)
    assert manifest.data["payload"]["sha256"] == sha256_hex


def test_validate_offline_snapshot_summary(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(FIXTURE.read_bytes())
    sha256_hex = compute_sha256_hex(payload)
    _write_manifest(
        tmp_path,
        payload_name="snapshot.jsonl",
        sha256_hex=sha256_hex,
        size_bytes=payload.stat().st_size,
        parts=["736", "740"],
    )
    summary = validate_offline_snapshot(payload)
    assert summary.section_count == 2
    assert summary.title_count == 1
    assert summary.payload_bytes == payload.stat().st_size


def test_validate_offline_snapshot_bad_null_text_fails_with_line(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(BAD_NULL_TEXT_FIXTURE.read_bytes())
    sha256_hex = compute_sha256_hex(payload)
    _write_manifest(tmp_path, payload_name="snapshot.jsonl", sha256_hex=sha256_hex, size_bytes=payload.stat().st_size)
    with pytest.raises(ValueError, match=r"snapshot\.jsonl:1 unexpected null text block in 'text'"):
        validate_offline_snapshot(payload)


def test_validate_offline_snapshot_bad_duplicate_fails_with_line(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(BAD_DUPLICATE_FIXTURE.read_bytes())
    sha256_hex = compute_sha256_hex(payload)
    _write_manifest(tmp_path, payload_name="snapshot.jsonl", sha256_hex=sha256_hex, size_bytes=payload.stat().st_size)
    with pytest.raises(ValueError, match=r"snapshot\.jsonl:2 duplicate section_id 'EAR-736\.2'"):
        validate_offline_snapshot(payload)
