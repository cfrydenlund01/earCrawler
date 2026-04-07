from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_corpus(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "section_id": "EAR-736.2(b)",
                        "doc_id": "EAR-736.2(b)",
                        "source_ref": "snapshot:test",
                        "text": "General prohibitions define when a license is required.",
                    }
                ),
                json.dumps(
                    {
                        "section_id": "EAR-740.1",
                        "doc_id": "EAR-740.1",
                        "source_ref": "snapshot:test",
                        "text": "License exceptions may authorize exports without a license.",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_training_contract(path: Path, *, corpus: Path, index_meta: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "training-input-contract.v1",
                "authoritative_sources": {
                    "retrieval_corpus_jsonl": str(corpus),
                    "faiss_index_meta_json": str(index_meta),
                },
            }
        ),
        encoding="utf-8",
    )


def _write_index_meta(path: Path, *, corpus_digest: str, doc_count: int) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "retriever-index-meta.v1",
                "corpus_digest": corpus_digest,
                "doc_count": doc_count,
            }
        ),
        encoding="utf-8",
    )


def _write_snapshot_manifest(path: Path, *, snapshot_id: str, snapshot_sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "manifest_version": "offline-snapshot.v1",
                "snapshot_id": snapshot_id,
                "payload": {
                    "path": "snapshot.jsonl",
                    "sha256": snapshot_sha256,
                },
            }
        ),
        encoding="utf-8",
    )


def _run_prepare_only(
    *,
    corpus: Path,
    out_root: Path,
    run_id: str,
    contract: Path,
    index_meta: Path,
    use_4bit: bool = False,
    require_qlora_4bit: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "scripts/training/run_phase5_finetune.py",
        "--prepare-only",
        "--retrieval-corpus",
        str(corpus),
        "--training-input-contract",
        str(contract),
        "--index-meta",
        str(index_meta),
        "--output-root",
        str(out_root),
        "--run-id",
        run_id,
        "--snapshot-id",
        "ecfr-title15-2026-02-28",
        "--snapshot-sha256",
        "abc123",
        "--max-examples",
        "4",
    ]
    if use_4bit:
        command.append("--use-4bit")
    if require_qlora_4bit:
        command.append("--require-qlora-4bit")
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_phase5_training_runner_prepare_only_writes_manifest_and_metadata(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest=_sha256_file(corpus),
        doc_count=2,
    )
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=corpus, index_meta=index_meta)

    out_root = tmp_path / "dist_training"
    run_id = "phase5-test-run"
    proc = _run_prepare_only(
        corpus=corpus,
        out_root=out_root,
        run_id=run_id,
        contract=contract,
        index_meta=index_meta,
    )
    assert proc.returncode == 0, proc.stdout

    run_dir = out_root / run_id
    manifest_path = run_dir / "manifest.json"
    examples_path = run_dir / "examples.jsonl"
    config_path = run_dir / "run_config.json"
    metadata_path = run_dir / "run_metadata.json"

    assert manifest_path.exists()
    assert examples_path.exists()
    assert config_path.exists()
    assert metadata_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "training-package.v1"
    assert manifest["base_model"] == "google/gemma-4-E4B-it"
    assert manifest["example_count"] == 4
    assert metadata["status"] == "prepare_only"
    assert metadata["prepare_only"] is True
    assert metadata["qlora"]["required"] is False
    assert metadata["qlora"]["requested_use_4bit"] is False
    assert metadata["qlora"]["effective_use_4bit"] is None


def test_phase5_training_runner_prepare_only_supports_qlora_packaging_without_runtime_cuda(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest=_sha256_file(corpus),
        doc_count=2,
    )
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=corpus, index_meta=index_meta)

    out_root = tmp_path / "dist_training"
    run_id = "phase5-prepare-only-qlora"
    proc = _run_prepare_only(
        corpus=corpus,
        out_root=out_root,
        run_id=run_id,
        contract=contract,
        index_meta=index_meta,
        use_4bit=True,
        require_qlora_4bit=True,
    )
    assert proc.returncode == 0, proc.stdout

    metadata_path = out_root / run_id / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "prepare_only"
    assert metadata["qlora"]["required"] is True
    assert metadata["qlora"]["requested_use_4bit"] is True
    assert metadata["qlora"]["effective_use_4bit"] is None
    assert metadata["qlora"]["evidence_status"] == "not_executed_prepare_only"


def test_phase5_training_runner_reports_missing_retrieval_corpus_as_preflight_failure(
    tmp_path: Path,
) -> None:
    missing_corpus = tmp_path / "missing_retrieval_corpus.jsonl"
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest="0" * 64,
        doc_count=0,
    )
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=missing_corpus, index_meta=index_meta)

    proc = _run_prepare_only(
        corpus=missing_corpus,
        out_root=tmp_path / "dist_training",
        run_id="phase5-missing-corpus",
        contract=contract,
        index_meta=index_meta,
    )

    assert proc.returncode == 2
    assert "Training corpus preflight failed: Retrieval corpus not found:" in proc.stdout


def test_phase5_training_runner_fails_when_contract_corpus_path_mismatches(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest=_sha256_file(corpus),
        doc_count=2,
    )
    wrong_corpus = tmp_path / "other_corpus.jsonl"
    _write_corpus(wrong_corpus)
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=wrong_corpus, index_meta=index_meta)

    proc = _run_prepare_only(
        corpus=corpus,
        out_root=tmp_path / "dist_training",
        run_id="phase5-bad-contract-path",
        contract=contract,
        index_meta=index_meta,
    )

    assert proc.returncode == 2
    assert "Training corpus preflight failed:" in proc.stdout
    assert "Configured retrieval corpus path does not match training input contract" in proc.stdout


def test_phase5_training_runner_fails_when_index_meta_digest_mismatches(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest="0" * 64,
        doc_count=2,
    )
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=corpus, index_meta=index_meta)

    proc = _run_prepare_only(
        corpus=corpus,
        out_root=tmp_path / "dist_training",
        run_id="phase5-bad-digest",
        contract=contract,
        index_meta=index_meta,
    )

    assert proc.returncode == 2
    assert "Training corpus preflight failed:" in proc.stdout
    assert "Retrieval corpus digest mismatch vs FAISS metadata" in proc.stdout


def test_phase5_training_runner_fails_when_index_meta_doc_count_mismatches(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest=_sha256_file(corpus),
        doc_count=3,
    )
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=corpus, index_meta=index_meta)

    proc = _run_prepare_only(
        corpus=corpus,
        out_root=tmp_path / "dist_training",
        run_id="phase5-bad-doc-count",
        contract=contract,
        index_meta=index_meta,
    )

    assert proc.returncode == 2
    assert "Training corpus preflight failed:" in proc.stdout
    assert "Retrieval corpus document count mismatch vs FAISS metadata" in proc.stdout


def test_phase5_training_runner_fails_when_snapshot_manifest_required_but_not_configured(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    snapshot_manifest = tmp_path / "snapshots" / "offline" / "approved" / "manifest.json"
    _write_snapshot_manifest(
        snapshot_manifest,
        snapshot_id="approved-snapshot",
        snapshot_sha256="a" * 64,
    )
    index_meta = tmp_path / "index.meta.json"
    index_meta.write_text(
        json.dumps(
            {
                "schema_version": "retriever-index-meta.v1",
                "corpus_digest": _sha256_file(corpus),
                "doc_count": 2,
                "snapshot": {
                    "snapshot_id": "approved-snapshot",
                    "snapshot_sha256": "a" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    contract = tmp_path / "training_input_contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "training-input-contract.v1",
                "authoritative_sources": {
                    "offline_snapshot_manifest": str(snapshot_manifest),
                    "offline_snapshot_payload": str(snapshot_manifest.parent / "snapshot.jsonl"),
                    "retrieval_corpus_jsonl": str(corpus),
                    "faiss_index_meta_json": str(index_meta),
                },
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/training/run_phase5_finetune.py",
            "--prepare-only",
            "--retrieval-corpus",
            str(corpus),
            "--training-input-contract",
            str(contract),
            "--index-meta",
            str(index_meta),
            "--output-root",
            str(tmp_path / "dist_training"),
            "--run-id",
            "phase5-missing-snapshot-manifest",
            "--snapshot-id",
            "approved-snapshot",
            "--snapshot-sha256",
            "a" * 64,
            "--max-examples",
            "4",
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert proc.returncode == 2
    assert "Training snapshot preflight failed:" in proc.stdout
    assert "Configured snapshot manifest is required by training input contract" in proc.stdout


def test_phase5_training_runner_fails_when_snapshot_manifest_mismatches_index_snapshot(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    snapshot_manifest = tmp_path / "snapshots" / "offline" / "approved" / "manifest.json"
    _write_snapshot_manifest(
        snapshot_manifest,
        snapshot_id="approved-snapshot",
        snapshot_sha256="a" * 64,
    )
    index_meta = tmp_path / "index.meta.json"
    index_meta.write_text(
        json.dumps(
            {
                "schema_version": "retriever-index-meta.v1",
                "corpus_digest": _sha256_file(corpus),
                "doc_count": 2,
                "snapshot": {
                    "snapshot_id": "stale-snapshot",
                    "snapshot_sha256": "a" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    contract = tmp_path / "training_input_contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "training-input-contract.v1",
                "authoritative_sources": {
                    "offline_snapshot_manifest": str(snapshot_manifest),
                    "offline_snapshot_payload": str(snapshot_manifest.parent / "snapshot.jsonl"),
                    "retrieval_corpus_jsonl": str(corpus),
                    "faiss_index_meta_json": str(index_meta),
                },
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/training/run_phase5_finetune.py",
            "--prepare-only",
            "--retrieval-corpus",
            str(corpus),
            "--training-input-contract",
            str(contract),
            "--index-meta",
            str(index_meta),
            "--snapshot-manifest",
            str(snapshot_manifest),
            "--snapshot-id",
            "approved-snapshot",
            "--snapshot-sha256",
            "a" * 64,
            "--output-root",
            str(tmp_path / "dist_training"),
            "--run-id",
            "phase5-stale-index-snapshot",
            "--max-examples",
            "4",
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert proc.returncode == 2
    assert "Training snapshot preflight failed:" in proc.stdout
    assert "FAISS index metadata snapshot_id does not match snapshot manifest" in proc.stdout


def test_phase5_training_runner_fails_when_qlora_required_without_4bit(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest=_sha256_file(corpus),
        doc_count=2,
    )
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=corpus, index_meta=index_meta)

    proc = _run_prepare_only(
        corpus=corpus,
        out_root=tmp_path / "dist_training",
        run_id="phase5-qlora-required-no-4bit",
        contract=contract,
        index_meta=index_meta,
        use_4bit=False,
        require_qlora_4bit=True,
    )

    assert proc.returncode == 2
    assert "Training QLoRA preflight failed:" in proc.stdout
    assert "use_4bit is false" in proc.stdout


def test_phase5_training_runner_rejects_placeholder_snapshot_fields(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus)
    index_meta = tmp_path / "index.meta.json"
    _write_index_meta(
        index_meta,
        corpus_digest=_sha256_file(corpus),
        doc_count=2,
    )
    contract = tmp_path / "training_input_contract.json"
    _write_training_contract(contract, corpus=corpus, index_meta=index_meta)

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/training/run_phase5_finetune.py",
            "--prepare-only",
            "--retrieval-corpus",
            str(corpus),
            "--training-input-contract",
            str(contract),
            "--index-meta",
            str(index_meta),
            "--output-root",
            str(tmp_path / "dist_training"),
            "--run-id",
            "phase5-placeholder-snapshot-fields",
            "--snapshot-id",
            "<snapshot_id>",
            "--snapshot-sha256",
            "<snapshot_sha256>",
            "--max-examples",
            "4",
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert proc.returncode == 2
    assert "Training snapshot preflight failed:" in proc.stdout
    assert "Configured snapshot_id cannot contain placeholder tokens." in proc.stdout

