from __future__ import annotations

import json
from pathlib import Path

from scripts.eval import validate_local_adapter_release_bundle as validator


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "training" / "run-1"
    adapter = run_dir / "adapter"
    adapter.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "manifest_version": "training-package.v1",
            "run_id": "run-1",
            "base_model": "Qwen/Qwen2.5-7B-Instruct",
            "snapshot_id": "ecfr-title15-2026-02-28",
            "snapshot_sha256": "a" * 64,
            "retrieval_corpus_path": "data/faiss/retrieval_corpus.jsonl",
            "retrieval_corpus_digest": "b" * 64,
            "retrieval_corpus_doc_count": 3040,
            "training_input_contract_path": "config/training_input_contract.example.json",
            "index_meta_path": "data/faiss/index.meta.json",
        },
    )
    _write_json(
        run_dir / "run_config.json",
        {
            "schema_version": "training-run-config.v1",
            "run_id": "run-1",
        },
    )
    _write_json(
        run_dir / "run_metadata.json",
        {
            "schema_version": "training-run-metadata.v1",
            "run_id": "run-1",
            "status": "completed",
            "git_head": "deadbeef",
        },
    )
    _write_json(
        run_dir / "inference_smoke.json",
        {
            "pass": True,
            "base_model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    _write_json(adapter / "adapter_config.json", {})
    _write_json(adapter / "tokenizer_config.json", {})
    return run_dir


def _make_benchmark_bundle(
    tmp_path: Path,
    run_dir: Path,
    *,
    answer_accuracy: float = 0.82,
) -> Path:
    bench_dir = tmp_path / "benchmarks" / "bundle-1"
    bench_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        bench_dir / "benchmark_manifest.json",
        {
            "manifest_version": "local-adapter-benchmark.v1",
            "training_run": {"run_dir": str(run_dir)},
        },
    )
    summary = {
        "schema_version": "local-adapter-benchmark.v1",
        "dataset_ids": [
            "ear_compliance.v2",
            "entity_obligations.v2",
            "unanswerable.v2",
        ],
        "training_run": {"run_dir": str(run_dir)},
        "smoke_precondition": {"status": "passed"},
        "conditions": {
            "local_adapter": {
                "answer_accuracy": answer_accuracy,
                "label_accuracy": 0.9,
                "unanswerable_accuracy": 1.0,
                "valid_citation_rate": 0.98,
                "supported_rate": 0.94,
                "overclaim_rate": 0.01,
                "strict_output_failure_rate": 0.0,
                "request_422_rate": 0.0,
                "request_503_rate": 0.0,
                "latency_ms": {"p95": 1200},
            },
            "retrieval_only": {
                "answer_accuracy": 0.6,
                "label_accuracy": 0.7,
                "unanswerable_accuracy": 0.9,
                "valid_citation_rate": 0.96,
                "supported_rate": 0.8,
                "overclaim_rate": 0.03,
                "strict_output_failure_rate": 0.0,
                "request_422_rate": 0.0,
                "request_503_rate": 0.0,
                "latency_ms": {"p95": 200},
            },
        },
    }
    _write_json(bench_dir / "benchmark_summary.json", summary)
    (bench_dir / "benchmark_summary.md").write_text("# summary\n", encoding="utf-8")
    _write_json(bench_dir / "benchmark_artifacts.json", {"conditions": {}})
    return bench_dir / "benchmark_summary.json"


def _make_smoke_report(tmp_path: Path, run_dir: Path) -> Path:
    smoke_report = tmp_path / "kg" / "reports" / "local-adapter-smoke.json"
    _write_json(
        smoke_report,
        {
            "status": "passed",
            "run_dir": str(run_dir),
            "provider": "local_adapter",
            "endpoint": "http://127.0.0.1:9001/v1/rag/answer",
            "trace_id": "t-1",
        },
    )
    return smoke_report


def test_validator_writes_release_evidence_manifest_for_passing_bundle(
    tmp_path: Path,
) -> None:
    run_dir = _make_run_dir(tmp_path)
    benchmark_summary = _make_benchmark_bundle(tmp_path, run_dir)
    smoke_report = _make_smoke_report(tmp_path, run_dir)

    out_path = run_dir / "release_evidence_manifest.json"
    rc = validator.main(
        [
            "--run-dir",
            str(run_dir),
            "--benchmark-summary",
            str(benchmark_summary),
            "--smoke-report",
            str(smoke_report),
            "--out",
            str(out_path),
        ]
    )

    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "local-adapter-release-evidence.v1"
    assert payload["decision"] == "ready_for_formal_promotion_review"
    assert payload["evidence_status"] == "complete"
    assert payload["training_run"]["retrieval_corpus_digest"] == "b" * 64


def test_validator_keeps_capability_optional_when_thresholds_fail(
    tmp_path: Path,
) -> None:
    run_dir = _make_run_dir(tmp_path)
    benchmark_summary = _make_benchmark_bundle(
        tmp_path, run_dir, answer_accuracy=0.4
    )
    smoke_report = _make_smoke_report(tmp_path, run_dir)

    out_path = run_dir / "release_evidence_manifest.json"
    rc = validator.main(
        [
            "--run-dir",
            str(run_dir),
            "--benchmark-summary",
            str(benchmark_summary),
            "--smoke-report",
            str(smoke_report),
            "--out",
            str(out_path),
        ]
    )

    assert rc == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["decision"] == "keep_optional"
    assert payload["evidence_status"] == "insufficient"
    assert any(
        "local_adapter.answer_accuracy" in item
        for item in payload["insufficient_evidence"]
    )
