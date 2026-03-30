from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = REPO_ROOT / "config" / "local_adapter_release_evidence.example.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_repo_path(raw: str) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def _looks_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "").strip().lower()))


def _require_mapping(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} is not a JSON object.")
    return dict(payload)


def _check_threshold(
    *,
    name: str,
    value: Any,
    min_value: Any = None,
    max_value: Any = None,
    failures: list[str],
) -> None:
    numeric = _as_float(value)
    if numeric is None:
        failures.append(f"Missing numeric metric: {name}")
        return
    if min_value is not None and numeric < float(min_value):
        failures.append(f"{name}={numeric:.4f} is below minimum {float(min_value):.4f}")
    if max_value is not None and numeric > float(max_value):
        failures.append(f"{name}={numeric:.4f} exceeds maximum {float(max_value):.4f}")


def _collect_required_paths(root: Path, relatives: list[str]) -> tuple[dict[str, str], list[str]]:
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for rel in relatives:
        path = (root / rel).resolve()
        resolved[rel] = str(path)
        if not path.exists():
            missing.append(rel)
    return resolved, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the minimum local-adapter release evidence bundle.")
    parser.add_argument("--run-dir", type=Path, required=True, help="Task 5.3 run directory (dist/training/<run_id>).")
    parser.add_argument("--benchmark-summary", type=Path, required=True, help="benchmark_summary.json from run_local_adapter_benchmark.py.")
    parser.add_argument("--smoke-report", type=Path, default=Path("kg") / "reports" / "local-adapter-smoke.json")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--out", type=Path, default=None, help="Output path for release_evidence_manifest.json.")
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()
    out_path = args.out.resolve() if args.out else (run_dir / "release_evidence_manifest.json").resolve()

    try:
        contract = _require_mapping(_read_json(args.contract.resolve()), "contract")
    except Exception as exc:
        print(f"Failed: cannot read contract: {exc}")
        return 2

    bundle_cfg = _require_mapping(contract.get("bundle"), "contract.bundle")
    thresholds = _require_mapping(contract.get("thresholds"), "contract.thresholds")
    comparisons = _require_mapping(contract.get("comparison_rules"), "contract.comparison_rules")
    decision_rule = _require_mapping(contract.get("decision_rule"), "contract.decision_rule")

    run_files = [str(item) for item in bundle_cfg.get("required_run_files") or []]
    benchmark_files = [str(item) for item in bundle_cfg.get("required_benchmark_files") or []]
    rollback_docs = [str(item) for item in bundle_cfg.get("rollback_docs") or []]
    required_datasets = [str(item) for item in bundle_cfg.get("required_primary_datasets") or []]

    run_paths, missing_run_files = _collect_required_paths(run_dir, run_files)

    benchmark_summary_path = args.benchmark_summary.resolve()
    benchmark_root = benchmark_summary_path.parent
    benchmark_paths, missing_benchmark_files = _collect_required_paths(benchmark_root, benchmark_files)
    rollback_path_map = {doc: str(_resolve_repo_path(doc)) for doc in rollback_docs}
    missing_rollback_docs = [doc for doc, path in rollback_path_map.items() if not Path(path).exists()]

    failures: list[str] = []
    candidate_execution_failures: list[str] = []
    insufficient: list[str] = []
    if missing_run_files:
        insufficient.append("Missing required run artifacts: " + ", ".join(sorted(missing_run_files)))
    if missing_benchmark_files:
        insufficient.append("Missing required benchmark artifacts: " + ", ".join(sorted(missing_benchmark_files)))
    if missing_rollback_docs:
        insufficient.append("Missing rollback docs: " + ", ".join(sorted(missing_rollback_docs)))

    manifest: dict[str, Any] = {}
    run_config: dict[str, Any] = {}
    run_metadata: dict[str, Any] = {}
    inference_smoke: dict[str, Any] = {}
    runtime_smoke: dict[str, Any] = {}
    benchmark_summary: dict[str, Any] = {}
    benchmark_manifest: dict[str, Any] = {}

    parse_failures: list[str] = []
    try:
        manifest = _require_mapping(_read_json(run_dir / "manifest.json"), "manifest.json")
    except Exception as exc:
        parse_failures.append(f"Cannot read manifest.json: {exc}")
    try:
        run_config = _require_mapping(_read_json(run_dir / "run_config.json"), "run_config.json")
    except Exception as exc:
        parse_failures.append(f"Cannot read run_config.json: {exc}")
    try:
        run_metadata = _require_mapping(_read_json(run_dir / "run_metadata.json"), "run_metadata.json")
    except Exception as exc:
        parse_failures.append(f"Cannot read run_metadata.json: {exc}")
    try:
        inference_smoke = _require_mapping(_read_json(run_dir / "inference_smoke.json"), "inference_smoke.json")
    except Exception as exc:
        parse_failures.append(f"Cannot read inference_smoke.json: {exc}")
    try:
        runtime_smoke = _require_mapping(_read_json(args.smoke_report.resolve()), "local-adapter-smoke.json")
    except Exception as exc:
        parse_failures.append(f"Cannot read smoke report: {exc}")
    try:
        benchmark_summary = _require_mapping(_read_json(benchmark_summary_path), "benchmark_summary.json")
    except Exception as exc:
        parse_failures.append(f"Cannot read benchmark_summary.json: {exc}")
    try:
        benchmark_manifest = _require_mapping(_read_json(benchmark_root / "benchmark_manifest.json"), "benchmark_manifest.json")
    except Exception as exc:
        parse_failures.append(f"Cannot read benchmark_manifest.json: {exc}")
    if parse_failures:
        insufficient.extend(parse_failures)

    runtime_smoke_path = args.smoke_report.resolve()
    runtime_smoke_sha256 = _sha256_file(runtime_smoke_path) if runtime_smoke_path.exists() else None

    manifest_checks: list[str] = []
    if manifest:
        if str(manifest.get("manifest_version") or "").strip() != "training-package.v1":
            manifest_checks.append("manifest.json manifest_version must equal training-package.v1")
        if not str(manifest.get("snapshot_id") or "").strip():
            manifest_checks.append("manifest.json is missing snapshot_id")
        if not _looks_sha256(str(manifest.get("snapshot_sha256") or "")):
            manifest_checks.append("manifest.json is missing a valid snapshot_sha256")
        if not _looks_sha256(str(manifest.get("retrieval_corpus_digest") or "")):
            manifest_checks.append("manifest.json is missing a valid retrieval_corpus_digest")
        if int(manifest.get("retrieval_corpus_doc_count") or 0) <= 0:
            manifest_checks.append("manifest.json retrieval_corpus_doc_count must be positive")
        if not str(manifest.get("training_input_contract_path") or "").strip():
            manifest_checks.append("manifest.json is missing training_input_contract_path")
    if manifest_checks:
        insufficient.extend(manifest_checks)

    metadata_checks: list[str] = []
    if run_metadata:
        if str(run_metadata.get("schema_version") or "").strip() != "training-run-metadata.v1":
            metadata_checks.append("run_metadata.json schema_version must equal training-run-metadata.v1")
        if str(run_metadata.get("status") or "").strip() != "completed":
            metadata_checks.append("run_metadata.json status must equal completed")
    if metadata_checks:
        insufficient.extend(metadata_checks)

    qlora_insufficient_checks: list[str] = []
    qlora_runtime_checks: list[str] = []
    qlora_contract_raw = contract.get("qlora")
    qlora_contract: dict[str, Any] = {}
    if qlora_contract_raw is not None:
        try:
            qlora_contract = _require_mapping(qlora_contract_raw, "contract.qlora")
        except ValueError as exc:
            qlora_insufficient_checks.append(str(exc))

    required_base_models = {
        str(item).strip()
        for item in qlora_contract.get("required_for_base_models") or []
        if str(item).strip()
    }
    qlora_required_for_candidate = bool(
        str(manifest.get("base_model") or "").strip() in required_base_models
    )
    if qlora_required_for_candidate:
        train_hyperparams = run_config.get("training_hyperparams")
        if not isinstance(train_hyperparams, Mapping):
            qlora_insufficient_checks.append(
                "run_config.json is missing training_hyperparams for QLoRA evidence."
            )
        else:
            use_4bit_value = train_hyperparams.get("use_4bit")
            if use_4bit_value is None:
                qlora_insufficient_checks.append(
                    "run_config.json training_hyperparams.use_4bit is missing."
                )
            elif not bool(use_4bit_value):
                qlora_runtime_checks.append(
                    "run_config.json training_hyperparams.use_4bit must equal true for a QLoRA-required candidate."
                )

        qlora_metadata = run_metadata.get("qlora")
        if not isinstance(qlora_metadata, Mapping):
            qlora_insufficient_checks.append(
                "run_metadata.json is missing qlora evidence."
            )
        else:
            required_flag = qlora_metadata.get("required")
            if required_flag is None:
                qlora_insufficient_checks.append(
                    "run_metadata.json qlora.required is missing."
                )
            elif not bool(required_flag):
                qlora_runtime_checks.append(
                    "run_metadata.json qlora.required must equal true for a QLoRA-required candidate."
                )

            requested_flag = qlora_metadata.get("requested_use_4bit")
            if requested_flag is None:
                qlora_insufficient_checks.append(
                    "run_metadata.json qlora.requested_use_4bit is missing."
                )
            elif not bool(requested_flag):
                qlora_runtime_checks.append(
                    "run_metadata.json qlora.requested_use_4bit must equal true for a QLoRA-required candidate."
                )

            effective_flag = qlora_metadata.get("effective_use_4bit")
            if effective_flag is None:
                qlora_insufficient_checks.append(
                    "run_metadata.json qlora.effective_use_4bit is missing."
                )
            elif not bool(effective_flag):
                qlora_runtime_checks.append(
                    "run_metadata.json qlora.effective_use_4bit must equal true for a QLoRA-required candidate."
                )

    if qlora_insufficient_checks:
        insufficient.extend(qlora_insufficient_checks)
    if qlora_runtime_checks:
        candidate_execution_failures.extend(qlora_runtime_checks)

    inference_checks: list[str] = []
    if inference_smoke:
        if not bool(inference_smoke.get("pass")):
            inference_checks.append("inference_smoke.json must record pass=true")
        if str(inference_smoke.get("base_model") or "").strip() != str(manifest.get("base_model") or "").strip():
            inference_checks.append("inference_smoke.json base_model must match manifest.json")
    if inference_checks:
        candidate_execution_failures.extend(inference_checks)

    runtime_checks: list[str] = []
    if runtime_smoke:
        if str(runtime_smoke.get("status") or "").strip().lower() != "passed":
            runtime_checks.append("local-adapter-smoke.json must record status=passed")
        if str(runtime_smoke.get("provider") or "").strip().lower() != "local_adapter":
            runtime_checks.append("local-adapter-smoke.json provider must equal local_adapter")
        smoke_run_dir = str(runtime_smoke.get("run_dir") or "").strip()
        if smoke_run_dir and Path(smoke_run_dir).resolve() != run_dir:
            runtime_checks.append("local-adapter-smoke.json run_dir does not match the candidate run_dir")
    if runtime_checks:
        candidate_execution_failures.extend(runtime_checks)

    benchmark_checks: list[str] = []
    benchmark_precondition_checks: list[str] = []
    if benchmark_summary:
        if str(benchmark_summary.get("schema_version") or "").strip() != "local-adapter-benchmark.v1":
            benchmark_checks.append("benchmark_summary.json schema_version must equal local-adapter-benchmark.v1")
        dataset_ids = {str(item) for item in benchmark_summary.get("dataset_ids") or []}
        missing_datasets = sorted(set(required_datasets) - dataset_ids)
        if missing_datasets:
            benchmark_checks.append("benchmark_summary.json is missing required datasets: " + ", ".join(missing_datasets))
        try:
            summary_run = _require_mapping(benchmark_summary.get("training_run"), "benchmark_summary.training_run")
            summary_run_dir = str(summary_run.get("run_dir") or "").strip()
            if summary_run_dir and Path(summary_run_dir).resolve() != run_dir:
                benchmark_checks.append("benchmark_summary.json training_run.run_dir does not match the candidate run_dir")
        except Exception as exc:
            benchmark_checks.append(str(exc))
        try:
            smoke_precondition = _require_mapping(benchmark_summary.get("smoke_precondition"), "benchmark_summary.smoke_precondition")
            if not bool(smoke_precondition.get("required")):
                benchmark_precondition_checks.append("benchmark_summary.json smoke_precondition.required must equal true")
            if not _looks_sha256(str(smoke_precondition.get("sha256") or "")):
                benchmark_precondition_checks.append("benchmark_summary.json smoke_precondition.sha256 must be a valid SHA-256")
            bundle_copy_path = str(smoke_precondition.get("bundle_copy_path") or "").strip()
            if not bundle_copy_path:
                benchmark_precondition_checks.append("benchmark_summary.json smoke_precondition.bundle_copy_path is missing")
            if str(smoke_precondition.get("status") or "").strip().lower() != "passed":
                candidate_execution_failures.append("benchmark_summary.json smoke_precondition.status must equal passed")
            if runtime_smoke_sha256 and str(smoke_precondition.get("sha256") or "").strip().lower() not in {"", runtime_smoke_sha256.lower()}:
                benchmark_precondition_checks.append("benchmark_summary.json smoke_precondition.sha256 does not match the reviewed runtime smoke report")
        except Exception as exc:
            benchmark_checks.append(str(exc))
    if benchmark_manifest:
        if str(benchmark_manifest.get("manifest_version") or "").strip() != "local-adapter-benchmark.v1":
            benchmark_checks.append("benchmark_manifest.json manifest_version must equal local-adapter-benchmark.v1")
        try:
            manifest_run = _require_mapping(benchmark_manifest.get("training_run"), "benchmark_manifest.training_run")
            manifest_run_dir = str(manifest_run.get("run_dir") or "").strip()
            if manifest_run_dir and Path(manifest_run_dir).resolve() != run_dir:
                benchmark_checks.append("benchmark_manifest.json training_run.run_dir does not match the candidate run_dir")
        except Exception as exc:
            benchmark_checks.append(str(exc))
        try:
            manifest_smoke = _require_mapping(benchmark_manifest.get("smoke_precondition"), "benchmark_manifest.smoke_precondition")
            if not bool(manifest_smoke.get("required")):
                benchmark_precondition_checks.append("benchmark_manifest.json smoke_precondition.required must equal true")
            if not _looks_sha256(str(manifest_smoke.get("source_sha256") or "")):
                benchmark_precondition_checks.append("benchmark_manifest.json smoke_precondition.source_sha256 must be a valid SHA-256")
            bundle_copy_path = str(manifest_smoke.get("bundle_copy_path") or "").strip()
            if not bundle_copy_path:
                benchmark_precondition_checks.append("benchmark_manifest.json smoke_precondition.bundle_copy_path is missing")
            if str(manifest_smoke.get("status") or "").strip().lower() != "passed":
                candidate_execution_failures.append("benchmark_manifest.json smoke_precondition.status must equal passed")
            if runtime_smoke_sha256 and str(manifest_smoke.get("source_sha256") or "").strip().lower() not in {"", runtime_smoke_sha256.lower()}:
                benchmark_precondition_checks.append("benchmark_manifest.json smoke_precondition.source_sha256 does not match the reviewed runtime smoke report")
        except Exception as exc:
            benchmark_checks.append(str(exc))
    benchmark_smoke_copy_path = benchmark_root / "preconditions" / "local_adapter_smoke.json"
    if benchmark_smoke_copy_path.exists() and runtime_smoke_sha256:
        copy_sha256 = _sha256_file(benchmark_smoke_copy_path)
        if copy_sha256.lower() != runtime_smoke_sha256.lower():
            benchmark_precondition_checks.append("benchmark preconditions/local_adapter_smoke.json does not match the reviewed runtime smoke report")
    if benchmark_checks:
        insufficient.extend(benchmark_checks)
    if benchmark_precondition_checks:
        insufficient.extend(benchmark_precondition_checks)

    local_metrics: dict[str, Any] = {}
    retrieval_metrics: dict[str, Any] = {}
    if benchmark_summary:
        conditions = benchmark_summary.get("conditions") or {}
        if isinstance(conditions, Mapping):
            local_raw = conditions.get("local_adapter")
            if isinstance(local_raw, Mapping):
                local_metrics = dict(local_raw)
            else:
                insufficient.append("benchmark_summary.json is missing conditions.local_adapter")
            if comparisons.get("require_retrieval_only_condition"):
                retrieval_raw = conditions.get("retrieval_only")
                if isinstance(retrieval_raw, Mapping):
                    retrieval_metrics = dict(retrieval_raw)
                else:
                    insufficient.append("benchmark_summary.json is missing conditions.retrieval_only")
        else:
            insufficient.append("benchmark_summary.json is missing conditions")

    if local_metrics:
        _check_threshold(name="local_adapter.answer_accuracy", value=local_metrics.get("answer_accuracy"), min_value=thresholds.get("answer_accuracy_min"), failures=failures)
        _check_threshold(name="local_adapter.label_accuracy", value=local_metrics.get("label_accuracy"), min_value=thresholds.get("label_accuracy_min"), failures=failures)
        _check_threshold(name="local_adapter.unanswerable_accuracy", value=local_metrics.get("unanswerable_accuracy"), min_value=thresholds.get("unanswerable_accuracy_min"), failures=failures)
        _check_threshold(name="local_adapter.valid_citation_rate", value=local_metrics.get("valid_citation_rate"), min_value=thresholds.get("valid_citation_rate_min"), failures=failures)
        _check_threshold(name="local_adapter.supported_rate", value=local_metrics.get("supported_rate"), min_value=thresholds.get("supported_rate_min"), failures=failures)
        _check_threshold(name="local_adapter.overclaim_rate", value=local_metrics.get("overclaim_rate"), max_value=thresholds.get("overclaim_rate_max"), failures=failures)
        _check_threshold(name="local_adapter.strict_output_failure_rate", value=local_metrics.get("strict_output_failure_rate"), max_value=thresholds.get("strict_output_failure_rate_max"), failures=failures)
        _check_threshold(name="local_adapter.request_422_rate", value=local_metrics.get("request_422_rate"), max_value=thresholds.get("request_422_rate_max"), failures=failures)
        _check_threshold(name="local_adapter.request_503_rate", value=local_metrics.get("request_503_rate"), max_value=thresholds.get("request_503_rate_max"), failures=failures)
        lat_raw = local_metrics.get("latency_ms")
        if isinstance(lat_raw, Mapping):
            lat = dict(lat_raw)
            _check_threshold(name="local_adapter.latency_ms.p95", value=lat.get("p95"), max_value=thresholds.get("latency_p95_ms_max"), failures=failures)
        else:
            failures.append("Missing numeric metric: local_adapter.latency_ms.p95")

    comparison_failures: list[str] = []
    if local_metrics and retrieval_metrics:
        local_answer = _as_float(local_metrics.get("answer_accuracy"))
        retrieval_answer = _as_float(retrieval_metrics.get("answer_accuracy"))
        if comparisons.get("answer_accuracy_gte_retrieval_only") and local_answer is not None and retrieval_answer is not None and local_answer < retrieval_answer:
            comparison_failures.append("local_adapter.answer_accuracy is below retrieval_only.answer_accuracy")
        local_supported = _as_float(local_metrics.get("supported_rate"))
        retrieval_supported = _as_float(retrieval_metrics.get("supported_rate"))
        if comparisons.get("supported_rate_gte_retrieval_only") and local_supported is not None and retrieval_supported is not None and local_supported < retrieval_supported:
            comparison_failures.append("local_adapter.supported_rate is below retrieval_only.supported_rate")
        local_overclaim = _as_float(local_metrics.get("overclaim_rate"))
        retrieval_overclaim = _as_float(retrieval_metrics.get("overclaim_rate"))
        if comparisons.get("overclaim_rate_lte_retrieval_only") and local_overclaim is not None and retrieval_overclaim is not None and local_overclaim > retrieval_overclaim:
            comparison_failures.append("local_adapter.overclaim_rate exceeds retrieval_only.overclaim_rate")

    failing_evidence = candidate_execution_failures + failures + comparison_failures
    all_findings = insufficient + failing_evidence
    if insufficient:
        decision = "keep_optional"
        candidate_review_status = "not_reviewable"
        evidence_status = "incomplete"
    elif failing_evidence:
        decision = "reject_candidate"
        candidate_review_status = "rejected"
        evidence_status = "complete"
    else:
        decision = "ready_for_formal_promotion_review"
        candidate_review_status = "ready_for_formal_promotion_review"
        evidence_status = "complete"

    payload = {
        "schema_version": "local-adapter-release-evidence.v1",
        "created_at_utc": _utc_now_iso(),
        "contract_path": str(args.contract.resolve()),
        "capability_id": str(contract.get("capability_id") or ""),
        "capability_state_after_validation": "optional",
        "candidate_review_status": candidate_review_status,
        "training_run": {
            "run_dir": str(run_dir),
            "manifest_path": str((run_dir / "manifest.json").resolve()),
            "run_config_path": str((run_dir / "run_config.json").resolve()),
            "run_metadata_path": str((run_dir / "run_metadata.json").resolve()),
            "inference_smoke_path": str((run_dir / "inference_smoke.json").resolve()),
            "adapter_dir": str((run_dir / "adapter").resolve()),
            "snapshot_id": manifest.get("snapshot_id"),
            "snapshot_sha256": manifest.get("snapshot_sha256"),
            "retrieval_corpus_path": manifest.get("retrieval_corpus_path"),
            "retrieval_corpus_digest": manifest.get("retrieval_corpus_digest"),
            "retrieval_corpus_doc_count": manifest.get("retrieval_corpus_doc_count"),
            "base_model": manifest.get("base_model"),
            "git_head": run_metadata.get("git_head"),
            "qlora": run_metadata.get("qlora"),
            "file_hashes": {
                rel: _sha256_file(Path(path)) for rel, path in run_paths.items() if Path(path).exists()
            }
        },
        "runtime_smoke": {
            "path": str(runtime_smoke_path),
            "sha256": runtime_smoke_sha256,
            "status": runtime_smoke.get("status"),
            "provider": runtime_smoke.get("provider"),
            "endpoint": runtime_smoke.get("endpoint"),
            "trace_id": runtime_smoke.get("trace_id")
        },
        "benchmark": {
            "root": str(benchmark_root),
            "summary_path": str(benchmark_summary_path),
            "summary_sha256": _sha256_file(benchmark_summary_path) if benchmark_summary_path.exists() else None,
            "manifest_path": str((benchmark_root / "benchmark_manifest.json").resolve()),
            "artifact_hashes": {
                rel: _sha256_file(Path(path)) for rel, path in benchmark_paths.items() if Path(path).exists()
            },
            "dataset_ids": benchmark_summary.get("dataset_ids") or [],
            "conditions": benchmark_summary.get("conditions") or {}
        },
        "rollback_docs": {
            "required": rollback_docs,
            "resolved": rollback_path_map
        },
        "checks": {
            "missing_run_files": sorted(missing_run_files),
            "missing_benchmark_files": sorted(missing_benchmark_files),
            "missing_rollback_docs": sorted(missing_rollback_docs),
            "manifest_checks": manifest_checks,
            "run_metadata_checks": metadata_checks,
            "inference_smoke_checks": inference_checks,
            "runtime_smoke_checks": runtime_checks,
            "benchmark_checks": benchmark_checks,
            "benchmark_precondition_checks": benchmark_precondition_checks,
            "qlora_insufficient_checks": qlora_insufficient_checks,
            "qlora_runtime_checks": qlora_runtime_checks,
            "candidate_execution_failures": candidate_execution_failures,
            "threshold_failures": failures,
            "comparison_failures": comparison_failures
        },
        "thresholds": thresholds,
        "decision_rule": decision_rule,
        "evidence_status": evidence_status,
        "decision": decision,
        "insufficient_evidence": insufficient,
        "failing_evidence": failing_evidence,
        "all_findings": all_findings
    }
    _write_json(out_path, payload)

    if decision == "ready_for_formal_promotion_review":
        print(f"Wrote passing release evidence manifest: {out_path}")
        return 0

    if decision == "reject_candidate":
        print(f"Release evidence reviewed the candidate and rejected it. Wrote manifest: {out_path}")
        return 1

    print(f"Release evidence is incomplete; capability stays optional. Wrote manifest: {out_path}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
