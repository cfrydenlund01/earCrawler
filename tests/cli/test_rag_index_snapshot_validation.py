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


def _write_eval_manifest(path: Path, *, dataset_file: Path, dataset_id: str = "entity_obligations.v2") -> Path:
    manifest = {
        "datasets": [
            {
                "id": dataset_id,
                "file": str(dataset_file),
            }
        ]
    }
    manifest_path = path / "eval_manifest.json"
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


def test_rag_index_rebuild_corpus_writes_deterministic_bundle(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(GOOD_FIXTURE.read_bytes())
    manifest = _write_manifest(tmp_path, payload_name="snapshot.jsonl", payload_path=payload)

    dataset_file = tmp_path / "entity_obligations.v2.jsonl"
    dataset_file.write_text(
        json.dumps({"id": "x1", "ear_sections": ["EAR-736.2(b)"]}) + "\n"
        + json.dumps({"id": "x2", "ear_sections": ["EAR-740.9"]}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    eval_manifest = _write_eval_manifest(tmp_path, dataset_file=dataset_file)

    runner = CliRunner()
    args = [
        "rag-index",
        "rebuild-corpus",
        "--snapshot",
        str(payload),
        "--snapshot-manifest",
        str(manifest),
        "--out-base",
        str(tmp_path / "dist"),
        "--dataset-manifest",
        str(eval_manifest),
    ]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "Smoke check passed:" in result.output

    out_dir = tmp_path / "dist" / "cli-test-snapshot"
    corpus_path = out_dir / "retrieval_corpus.jsonl"
    build_log_path = out_dir / "build_log.json"
    assert corpus_path.exists()
    assert build_log_path.exists()

    docs = [
        json.loads(line)
        for line in corpus_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert docs
    assert all("part" in doc for doc in docs)
    assert {"EAR-736.2(b)", "EAR-740.9"}.issubset({doc["section_id"] for doc in docs})

    build_log = json.loads(build_log_path.read_text(encoding="utf-8"))
    assert build_log["snapshot"]["snapshot_id"] == "cli-test-snapshot"
    assert build_log["smoke"]["contract_errors"] == 0
    assert build_log["smoke"]["missing_expected_sections"] == []
    assert build_log["corpus"]["digest"]
    assert build_log["corpus"]["sha256"]

    corpus_first = corpus_path.read_bytes()
    build_log_first = build_log_path.read_bytes()
    result_second = runner.invoke(cli, args)
    assert result_second.exit_code == 0, result_second.output
    assert corpus_first == corpus_path.read_bytes()
    assert build_log_first == build_log_path.read_bytes()


def test_rag_index_rebuild_corpus_fails_when_expected_sections_missing(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.jsonl"
    payload.write_bytes(GOOD_FIXTURE.read_bytes())
    manifest = _write_manifest(tmp_path, payload_name="snapshot.jsonl", payload_path=payload)

    dataset_file = tmp_path / "entity_obligations.v2.jsonl"
    dataset_file.write_text(
        json.dumps({"id": "x1", "ear_sections": ["EAR-999.1"]}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    eval_manifest = _write_eval_manifest(tmp_path, dataset_file=dataset_file)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "rag-index",
            "rebuild-corpus",
            "--snapshot",
            str(payload),
            "--snapshot-manifest",
            str(manifest),
            "--out-base",
            str(tmp_path / "dist"),
            "--dataset-manifest",
            str(eval_manifest),
        ],
    )
    assert result.exit_code != 0
    assert "Corpus missing expected section IDs" in result.output
