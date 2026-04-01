from __future__ import annotations

import json
from pathlib import Path

from scripts.eval import run_local_adapter_benchmark as bench


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "training" / "run-1"
    adapter = run_dir / "adapter"
    adapter.mkdir(parents=True)
    _write_json(adapter / "adapter_config.json", {})
    _write_json(adapter / "tokenizer_config.json", {})
    _write_json(
        run_dir / "manifest.json",
        {
            "manifest_version": "training-package.v1",
            "run_id": "run-1",
            "base_model": "Qwen/Qwen2.5-7B-Instruct",
            "snapshot_id": "ecfr-title15-2026-02-28",
            "retrieval_corpus_digest": "a" * 64,
        },
    )
    _write_json(
        run_dir / "run_metadata.json",
        {
            "schema_version": "training-run-metadata.v1",
            "status": "completed",
            "artifact_dir": str(adapter.resolve()),
            "git_head": "deadbeef",
        },
    )
    _write_json(
        run_dir / "inference_smoke.json",
        {"base_model": "Qwen/Qwen2.5-7B-Instruct", "pass": True},
    )
    return run_dir


def _make_response(status_code: int, payload: dict, *, text: str = ""):
    class _Resp:
        def __init__(self) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self) -> dict:
            return self._payload

    return _Resp()


def test_runner_writes_bundle_and_summary(monkeypatch, tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    dataset_path = tmp_path / "eval" / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Does this require a license?",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = tmp_path / "eval" / "manifest.json"
    _write_json(
        manifest_path,
        {
            "datasets": [{"id": "ds1", "file": str(dataset_path), "task": "ear_compliance", "version": 1}],
            "references": {"sections": {}},
        },
    )
    smoke_report = tmp_path / "kg" / "reports" / "local-adapter-smoke.json"
    _write_json(smoke_report, {"status": "passed", "run_dir": str(run_dir), "provider": "local_adapter"})

    monkeypatch.setattr(bench, "ensure_valid_datasets", lambda **_kwargs: None)

    responses = [
        {
            "status_code": 200,
            "payload": {
                "output_ok": True,
                "provider": "local_adapter",
                "model": "run-1",
                "label": "true",
                "answer": "Yes",
                "citations": [],
                "contexts": [],
                "retrieved": [],
                "trace_id": "warmup-1",
            },
        },
        {
            "status_code": 200,
            "payload": {
                "output_ok": True,
                "provider": "local_adapter",
                "model": "run-1",
                "label": "true",
                "answer": "Yes",
                "citations": [],
                "contexts": [],
                "retrieved": [],
                "trace_id": "t1",
            },
        },
        {
            "status_code": 200,
            "payload": {
                "output_ok": True,
                "provider": "local_adapter",
                "model": "run-1",
                "label": "unanswerable",
                "answer": "",
                "citations": [],
                "contexts": [],
                "retrieved": [],
                "trace_id": "t2",
            },
        },
    ]

    def _post(*_args, **_kwargs):
        assert responses
        payload = responses.pop(0)
        return _make_response(payload["status_code"], payload["payload"])

    monkeypatch.setattr(bench.requests.Session, "post", _post)

    out_root = tmp_path / "dist" / "benchmarks"
    rc = bench.main(
        [
            "--run-dir",
            str(run_dir),
            "--manifest",
            str(manifest_path),
            "--dataset-id",
            "ds1",
            "--smoke-report",
            str(smoke_report),
            "--out-root",
            str(out_root),
            "--run-id",
            "benchmark_test",
            "--base-url",
            "http://127.0.0.1:9999",
        ]
    )
    assert rc == 0

    bundle_dir = out_root / "benchmark_test"
    assert (bundle_dir / "benchmark_manifest.json").exists()
    assert (bundle_dir / "benchmark_summary.json").exists()
    assert (bundle_dir / "benchmark_summary.md").exists()
    assert (bundle_dir / "preconditions" / "local_adapter_smoke.json").exists()
    assert (bundle_dir / "preconditions" / "local_adapter_warmup.json").exists()
    assert (bundle_dir / "conditions" / "local_adapter" / "ds1.json").exists()
    assert (bundle_dir / "conditions" / "retrieval_only" / "ds1.json").exists()

    summary = json.loads((bundle_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == "local-adapter-benchmark.v1"
    assert summary["smoke_precondition"]["required"] is True
    assert summary["smoke_precondition"]["bundle_copy_path"] == str((bundle_dir / "preconditions" / "local_adapter_smoke.json").resolve())
    assert summary["warmup_precondition"]["required"] is True
    assert summary["warmup_precondition"]["status"] == "passed"
    assert summary["conditions"]["local_adapter"]["num_items"] == 1
    assert summary["conditions"]["local_adapter"]["request_422_count"] == 0
    assert summary["condition_artifact_paths"]["local_adapter"]["ds1"].endswith("conditions\\local_adapter\\ds1.json") or summary["condition_artifact_paths"]["local_adapter"]["ds1"].endswith("conditions/local_adapter/ds1.json")

    manifest = json.loads((bundle_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert summary["benchmark_config"]["config_hash"] == manifest["config_hash"]
    assert manifest["smoke_precondition"]["required"] is True
    assert manifest["smoke_precondition"]["status"] == "passed"
    assert manifest["smoke_precondition"]["bundle_copy_path"] == str((bundle_dir / "preconditions" / "local_adapter_smoke.json").resolve())
    assert manifest["summary_json_sha256"]
    assert manifest["artifacts_json_sha256"]
    assert manifest["training_run"]["run_id"] == "run-1"


def test_runner_records_422_failures(monkeypatch, tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    dataset_path = tmp_path / "eval" / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Q?",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = tmp_path / "eval" / "manifest.json"
    _write_json(manifest_path, {"datasets": [{"id": "ds1", "file": str(dataset_path)}], "references": {"sections": {}}})
    smoke_report = tmp_path / "kg" / "reports" / "local-adapter-smoke.json"
    _write_json(smoke_report, {"status": "passed", "run_dir": str(run_dir), "provider": "local_adapter"})

    monkeypatch.setattr(bench, "ensure_valid_datasets", lambda **_kwargs: None)

    responses = [
        _make_response(
            200,
            {
                "output_ok": True,
                "provider": "local_adapter",
                "label": "true",
                "answer": "Yes",
                "citations": [],
                "contexts": [],
                "retrieved": [],
            },
        ),
        _make_response(
            422,
            {
                "output_ok": False,
                "provider": "local_adapter",
                "label": "",
                "answer": "",
                "citations": [],
                "contexts": [],
                "retrieved": [],
            },
        ),
    ]

    monkeypatch.setattr(bench.requests.Session, "post", lambda *_a, **_k: responses.pop(0))

    out_root = tmp_path / "dist" / "benchmarks"
    rc = bench.main(
        [
            "--run-dir",
            str(run_dir),
            "--manifest",
            str(manifest_path),
            "--dataset-id",
            "ds1",
            "--smoke-report",
            str(smoke_report),
            "--out-root",
            str(out_root),
            "--run-id",
            "benchmark_422",
            "--no-include-retrieval-control",
        ]
    )
    assert rc == 0
    summary = json.loads((out_root / "benchmark_422" / "benchmark_summary.json").read_text(encoding="utf-8"))
    local = summary["conditions"]["local_adapter"]
    assert local["request_422_count"] == 1
    assert local["request_422_rate"] == 1.0
    assert local["transport_failure_count"] == 0
    assert local["transport_failure_rate"] == 0.0


def test_runner_aborts_after_consecutive_transport_failures(monkeypatch, tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    dataset_path = tmp_path / "eval" / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Q1?",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            },
            {
                "id": "item-2",
                "task": "ear_compliance",
                "question": "Q2?",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            },
        ],
    )
    manifest_path = tmp_path / "eval" / "manifest.json"
    _write_json(manifest_path, {"datasets": [{"id": "ds1", "file": str(dataset_path)}], "references": {"sections": {}}})
    smoke_report = tmp_path / "kg" / "reports" / "local-adapter-smoke.json"
    _write_json(smoke_report, {"status": "passed", "run_dir": str(run_dir), "provider": "local_adapter"})

    monkeypatch.setattr(bench, "ensure_valid_datasets", lambda **_kwargs: None)

    calls = {"post": 0, "get": 0}

    def _post(*_args, **_kwargs):
        calls["post"] += 1
        if calls["post"] == 1:
            return _make_response(
                200,
                {
                    "output_ok": True,
                    "provider": "local_adapter",
                    "label": "true",
                    "answer": "Yes",
                    "citations": [],
                    "contexts": [],
                    "retrieved": [],
                },
            )
        raise bench.requests.ReadTimeout("read timeout")

    class _HealthResp:
        status_code = 503
        text = ""

        @staticmethod
        def json() -> dict:
            return {"status": "degraded"}

    def _get(*_args, **_kwargs):
        calls["get"] += 1
        return _HealthResp()

    monkeypatch.setattr(bench.requests.Session, "post", _post)
    monkeypatch.setattr(bench.requests.Session, "get", _get)

    out_root = tmp_path / "dist" / "benchmarks"
    rc = bench.main(
        [
            "--run-dir",
            str(run_dir),
            "--manifest",
            str(manifest_path),
            "--dataset-id",
            "ds1",
            "--smoke-report",
            str(smoke_report),
            "--out-root",
            str(out_root),
            "--run-id",
            "benchmark_abort",
            "--max-consecutive-transport-failures",
            "2",
        ]
    )

    assert rc == 1
    assert calls["post"] == 3
    assert calls["get"] == 1
    failure = json.loads((out_root / "benchmark_abort" / "benchmark_failure.json").read_text(encoding="utf-8"))
    assert failure["status"] == "aborted_transport_failure"
    assert failure["condition"] == "local_adapter"
    assert failure["dataset_id"] == "ds1"
    assert failure["processed_items"] == 2
    assert failure["consecutive_transport_failures"] == 2
    assert failure["transport_error"] == "read_timeout"
    assert failure["health_probe"]["ok"] is False


def test_runner_fails_when_local_adapter_warmup_returns_500(monkeypatch, tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    dataset_path = tmp_path / "eval" / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Q1?",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            },
        ],
    )
    manifest_path = tmp_path / "eval" / "manifest.json"
    _write_json(manifest_path, {"datasets": [{"id": "ds1", "file": str(dataset_path)}], "references": {"sections": {}}})
    smoke_report = tmp_path / "kg" / "reports" / "local-adapter-smoke.json"
    _write_json(smoke_report, {"status": "passed", "run_dir": str(run_dir), "provider": "local_adapter"})

    monkeypatch.setattr(bench, "ensure_valid_datasets", lambda **_kwargs: None)
    monkeypatch.setattr(
        bench.requests.Session,
        "post",
        lambda *_a, **_k: _make_response(500, {"title": "Internal Server Error", "detail": "boom"}),
    )
    monkeypatch.setattr(
        bench.requests.Session,
        "get",
        lambda *_a, **_k: _make_response(200, {"status": "ok"}),
    )

    out_root = tmp_path / "dist" / "benchmarks"
    rc = bench.main(
        [
            "--run-dir",
            str(run_dir),
            "--manifest",
            str(manifest_path),
            "--dataset-id",
            "ds1",
            "--smoke-report",
            str(smoke_report),
            "--out-root",
            str(out_root),
            "--run-id",
            "benchmark_warmup_fail",
        ]
    )

    assert rc == 1
    failure = json.loads((out_root / "benchmark_warmup_fail" / "benchmark_failure.json").read_text(encoding="utf-8"))
    assert failure["status"] == "warmup_failed"
    assert failure["warmup"]["status_code"] == 500


def test_runner_blocks_incomplete_training_run_before_benchmarking(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    _write_json(
        run_dir / "run_metadata.json",
        {
            "schema_version": "training-run-metadata.v1",
            "status": "prepare_only",
            "artifact_dir": str((run_dir / "adapter").resolve()),
        },
    )
    manifest_path = tmp_path / "eval" / "manifest.json"
    _write_json(manifest_path, {"datasets": [], "references": {"sections": {}}})
    smoke_report = tmp_path / "kg" / "reports" / "local-adapter-smoke.json"
    _write_json(smoke_report, {"status": "passed", "run_dir": str(run_dir), "provider": "local_adapter"})

    rc = bench.main(
        [
            "--run-dir",
            str(run_dir),
            "--manifest",
            str(manifest_path),
            "--smoke-report",
            str(smoke_report),
        ]
    )

    assert rc == 1
