from __future__ import annotations

import json
from pathlib import Path

from scripts.eval import build_local_adapter_candidate_bundle as bundle


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
    _write_json(run_dir / "run_config.json", {"schema_version": "training-run-config.v1"})
    _write_json(
        run_dir / "run_metadata.json",
        {
            "schema_version": "training-run-metadata.v1",
            "run_id": "run-1",
            "status": "completed",
            "artifact_dir": str(adapter.resolve()),
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
    _write_json(adapter / "adapter_model.safetensors", {"fake": "weights"})
    return run_dir


def _make_smoke_report(tmp_path: Path, run_dir: Path) -> Path:
    smoke_report = tmp_path / "kg" / "reports" / "local-adapter-smoke.json"
    _write_json(
        smoke_report,
        {
            "status": "passed",
            "run_dir": str(run_dir),
            "provider": "local_adapter",
            "endpoint": "http://127.0.0.1:9001/v1/rag/answer",
            "trace_id": "trace-1",
        },
    )
    return smoke_report


def _make_contract(tmp_path: Path) -> Path:
    rollback_root = tmp_path / "docs"
    rollback_root.mkdir(parents=True, exist_ok=True)
    for name in ("local_adapter_release_evidence.md", "capability_graduation_boundaries.md"):
        (rollback_root / name).write_text(f"# {name}\n", encoding="utf-8")
    ops_dir = rollback_root / "ops"
    ops_dir.mkdir(parents=True, exist_ok=True)
    (ops_dir / "windows_single_host_operator.md").write_text(
        "# windows_single_host_operator.md\n", encoding="utf-8"
    )
    contract_path = tmp_path / "config" / "local_adapter_release_evidence.example.json"
    _write_json(
        contract_path,
        {
            "schema_version": "local-adapter-release-evidence-contract.v2",
            "capability_id": "runtime.local_adapter_serving",
            "bundle": {
                "provenance_manifest": "dist/training/<run_id>/release_evidence_manifest.json",
                "required_run_files": [
                    "manifest.json",
                    "run_config.json",
                    "run_metadata.json",
                    "inference_smoke.json",
                    "adapter/adapter_config.json",
                    "adapter/tokenizer_config.json",
                ],
                "required_benchmark_files": [
                    "benchmark_manifest.json",
                    "benchmark_summary.json",
                    "benchmark_summary.md",
                    "benchmark_artifacts.json",
                    "preconditions/local_adapter_smoke.json",
                ],
                "required_primary_datasets": [
                    "ear_compliance.v2",
                    "entity_obligations.v2",
                    "unanswerable.v2",
                ],
                "rollback_docs": [
                    str(rollback_root / "local_adapter_release_evidence.md"),
                    str(rollback_root / "capability_graduation_boundaries.md"),
                    str(ops_dir / "windows_single_host_operator.md"),
                ],
            },
            "thresholds": {
                "answer_accuracy_min": 0.65,
                "label_accuracy_min": 0.8,
                "unanswerable_accuracy_min": 0.9,
                "valid_citation_rate_min": 0.95,
                "supported_rate_min": 0.9,
                "overclaim_rate_max": 0.05,
                "strict_output_failure_rate_max": 0.0,
                "request_422_rate_max": 0.0,
                "request_503_rate_max": 0.0,
                "latency_p95_ms_max": 15000,
            },
            "comparison_rules": {
                "require_retrieval_only_condition": True,
                "answer_accuracy_gte_retrieval_only": True,
                "supported_rate_gte_retrieval_only": True,
                "overclaim_rate_lte_retrieval_only": True,
            },
            "decision_rule": {
                "keep_optional_when": [],
                "reject_candidate_when": [],
                "ready_for_formal_promotion_review_when": [],
            },
        },
    )
    return contract_path


def _make_benchmark_bundle(tmp_path: Path, run_dir: Path, smoke_report: Path) -> Path:
    bench_dir = tmp_path / "benchmarks" / "bundle-1"
    smoke_copy = bench_dir / "preconditions" / "local_adapter_smoke.json"
    smoke_copy.parent.mkdir(parents=True, exist_ok=True)
    smoke_copy.write_text(smoke_report.read_text(encoding="utf-8"), encoding="utf-8")
    _write_json(
        bench_dir / "benchmark_summary.json",
        {
            "schema_version": "local-adapter-benchmark.v1",
            "dataset_ids": [
                "ear_compliance.v2",
                "entity_obligations.v2",
                "unanswerable.v2",
            ],
            "training_run": {"run_dir": str(run_dir)},
            "smoke_precondition": {
                "required": True,
                "path": str(smoke_report),
                "bundle_copy_path": str(smoke_copy.resolve()),
                "sha256": bundle._sha256_file(smoke_report),
                "status": "passed",
            },
            "conditions": {
                "local_adapter": {
                    "answer_accuracy": 0.82,
                    "label_accuracy": 0.9,
                    "unanswerable_accuracy": 1.0,
                    "valid_citation_rate": 0.99,
                    "supported_rate": 0.95,
                    "overclaim_rate": 0.01,
                    "strict_output_failure_rate": 0.0,
                    "request_422_rate": 0.0,
                    "request_503_rate": 0.0,
                    "latency_ms": {"p95": 1000},
                },
                "retrieval_only": {
                    "answer_accuracy": 0.6,
                    "label_accuracy": 0.8,
                    "unanswerable_accuracy": 0.9,
                    "valid_citation_rate": 0.98,
                    "supported_rate": 0.9,
                    "overclaim_rate": 0.02,
                    "strict_output_failure_rate": 0.0,
                    "request_422_rate": 0.0,
                    "request_503_rate": 0.0,
                    "latency_ms": {"p95": 200},
                },
            },
        },
    )
    _write_json(
        bench_dir / "benchmark_manifest.json",
        {
            "manifest_version": "local-adapter-benchmark.v1",
            "training_run": {"run_dir": str(run_dir)},
            "smoke_precondition": {
                "required": True,
                "source_path": str(smoke_report),
                "bundle_copy_path": str(smoke_copy.resolve()),
                "source_sha256": bundle._sha256_file(smoke_report),
                "status": "passed",
            },
        },
    )
    (bench_dir / "benchmark_summary.md").write_text("# summary\n", encoding="utf-8")
    _write_json(bench_dir / "benchmark_artifacts.json", {"conditions": {}})
    return bench_dir / "benchmark_summary.json"


def test_builder_writes_reviewable_candidate_bundle(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    smoke_report = _make_smoke_report(tmp_path, run_dir)
    benchmark_summary = _make_benchmark_bundle(tmp_path, run_dir, smoke_report)
    contract = _make_contract(tmp_path)
    out_root = tmp_path / "dist" / "reviewable_candidates"

    rc = bundle.main(
        [
            "--run-dir",
            str(run_dir),
            "--benchmark-summary",
            str(benchmark_summary),
            "--smoke-report",
            str(smoke_report),
            "--contract",
            str(contract),
            "--out-root",
            str(out_root),
        ]
    )

    assert rc == 0
    bundle_dir = out_root / "local_adapter_candidate_run-1_bundle-1"
    manifest = json.loads((bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "local-adapter-review-bundle.v1"
    assert manifest["decision"] == "ready_for_formal_promotion_review"
    assert (bundle_dir / "training" / "release_evidence_manifest.json").exists()
    assert (bundle_dir / "benchmark" / "benchmark_summary.json").exists()
    assert (bundle_dir / "runtime" / "local-adapter-smoke.json").exists()
    assert (bundle_dir / "docs" / "rollback" / "windows_single_host_operator.md").exists()
