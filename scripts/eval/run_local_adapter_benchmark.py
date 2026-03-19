from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import requests

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.validate_datasets import ensure_valid_datasets
from earCrawler.eval.citation_metrics import extract_ground_truth_sections, extract_predicted_sections, score_citations
from earCrawler.eval.groundedness_gates import evaluate_groundedness_signals, finalize_groundedness_metrics
from earCrawler.rag.pipeline import _normalize_section_id

PRIMARY_DATASETS: tuple[str, ...] = (
    "ear_compliance.v2",
    "entity_obligations.v2",
    "unanswerable.v2",
)
SUMMARY_VERSION = "local-adapter-benchmark.v1"
TRAINING_MANIFEST_VERSION = "training-package.v1"
RUN_METADATA_VERSION = "training-run-metadata.v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_name(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "unknown"
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)).strip("._-") or "unknown"


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


def _json_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _copy_json(src: Path, dst: Path) -> None:
    _write_json(dst, _read_json(src))


def _resolve_schema_path(manifest_path: Path) -> Path:
    for candidate in (manifest_path.parent / "schema.json", Path("eval") / "schema.json", _REPO_ROOT / "eval" / "schema.json"):
        if candidate.exists():
            return candidate
    return _REPO_ROOT / "eval" / "schema.json"


def _resolve_dataset(manifest: dict[str, Any], dataset_id: str, manifest_path: Path) -> tuple[dict[str, Any], Path]:
    for entry in manifest.get("datasets", []):
        if str(entry.get("id") or "") != dataset_id:
            continue
        path = Path(str(entry.get("file") or ""))
        if path.is_absolute() or path.exists():
            return entry, path
        return entry, manifest_path.parent / path
    raise ValueError(f"Dataset not found in manifest: {dataset_id}")


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    yield obj


def _normalize_answer(text: str) -> str:
    value = (text or "").strip().casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\n\r\"'`.,:;!?")


def _answer_ok(gt: str, pred: str, mode: str, threshold: float) -> bool:
    if not gt or not pred:
        return False
    if mode == "exact":
        return pred == gt
    if mode == "normalized":
        return _normalize_answer(pred) == _normalize_answer(gt)
    import difflib

    return difflib.SequenceMatcher(None, pred.casefold(), gt.casefold()).ratio() >= threshold


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * q
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(ordered[lo])
    frac = rank - lo
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


def _git_head_dirty() -> dict[str, Any]:
    def _run(argv: list[str]) -> tuple[int, str]:
        try:
            proc = subprocess.run(argv, cwd=str(_REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", check=False)
            return int(proc.returncode), (proc.stdout or "").strip()
        except Exception:
            return 1, ""

    rc1, head = _run(["git", "rev-parse", "HEAD"])
    rc2, status = _run(["git", "status", "--porcelain"])
    dirty = bool([line for line in status.splitlines() if line.strip()]) if rc2 == 0 else False
    return {"git_head": head if rc1 == 0 else "", "git_dirty": dirty}


def _looks_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "").strip().lower()))


def _assert_run_dir(run_dir: Path) -> dict[str, Any]:
    resolved = run_dir.resolve()
    adapter = resolved / "adapter"
    required = [
        adapter,
        adapter / "adapter_config.json",
        adapter / "tokenizer_config.json",
        resolved / "manifest.json",
        resolved / "run_metadata.json",
        resolved / "inference_smoke.json",
    ]
    for path in required:
        if not path.exists():
            raise ValueError(f"Missing required run artifact: {path}")
    manifest = _read_json(resolved / "manifest.json")
    if str(manifest.get("manifest_version") or "").strip() != TRAINING_MANIFEST_VERSION:
        raise ValueError(
            "Run manifest is malformed: manifest_version must equal "
            f"{TRAINING_MANIFEST_VERSION}."
        )
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Run manifest is malformed: run_id is required.")
    base_model = str(manifest.get("base_model") or "").strip()
    if not base_model:
        raise ValueError("Run manifest is malformed: base_model is required.")
    snapshot_id = str(manifest.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("Run manifest is malformed: snapshot_id is required.")
    retrieval_corpus_digest = str(manifest.get("retrieval_corpus_digest") or "").strip()
    if not _looks_sha256(retrieval_corpus_digest):
        raise ValueError(
            "Run manifest is malformed: retrieval_corpus_digest must be a SHA-256."
        )

    run_metadata = _read_json(resolved / "run_metadata.json")
    if str(run_metadata.get("schema_version") or "").strip() != RUN_METADATA_VERSION:
        raise ValueError(
            "Run metadata is malformed: schema_version must equal "
            f"{RUN_METADATA_VERSION}."
        )
    if str(run_metadata.get("status") or "").strip() != "completed":
        raise ValueError(
            "Run metadata is incomplete: status must equal completed before "
            "benchmarking."
        )
    artifact_dir = str(run_metadata.get("artifact_dir") or "").strip()
    if artifact_dir and Path(artifact_dir).resolve() != adapter:
        raise ValueError("Run metadata artifact_dir does not match the adapter directory.")

    inference_smoke = _read_json(resolved / "inference_smoke.json")
    if not bool(inference_smoke.get("pass")):
        raise ValueError("Inference smoke is incomplete: pass must equal true.")
    if str(inference_smoke.get("base_model") or "").strip() != base_model:
        raise ValueError("Inference smoke base_model does not match the run manifest.")
    return {
        "run_dir": str(resolved),
        "run_id": run_id,
        "adapter_dir": str(adapter),
        "manifest_path": str(resolved / "manifest.json"),
        "manifest_sha256": _sha256_file(resolved / "manifest.json"),
        "run_metadata_path": str(resolved / "run_metadata.json"),
        "run_metadata_sha256": _sha256_file(resolved / "run_metadata.json"),
        "inference_smoke_path": str(resolved / "inference_smoke.json"),
        "inference_smoke_sha256": _sha256_file(resolved / "inference_smoke.json"),
        "base_model": base_model,
        "snapshot_id": snapshot_id,
        "retrieval_corpus_digest": retrieval_corpus_digest,
        "git_head": str(run_metadata.get("git_head") or ""),
    }


def _load_smoke(smoke_report: Path, run_dir: Path) -> dict[str, Any]:
    if not smoke_report.exists():
        raise ValueError(f"Smoke report not found: {smoke_report}")
    payload = _read_json(smoke_report)
    if str(payload.get("status") or "").strip().lower() != "passed":
        raise ValueError(f"Smoke report is not passed: {smoke_report}")
    report_run_dir = str(payload.get("run_dir") or "").strip()
    if report_run_dir and Path(report_run_dir).resolve() != run_dir.resolve():
        raise ValueError("Smoke report run_dir does not match benchmark run_dir.")
    provider = str(payload.get("provider") or "").strip().lower()
    if provider and provider != "local_adapter":
        raise ValueError(f"Smoke report provider must be local_adapter, got {provider!r}")
    return payload


def _call_answer(
    *,
    session: requests.Session,
    base_url: str,
    api_key: str | None,
    query: str,
    top_k: int,
    generate: bool,
    timeout: float,
) -> tuple[int, dict[str, Any], float, str | None]:
    url = f"{base_url.rstrip('/')}/v1/rag/answer"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    payload = {"query": query, "top_k": int(top_k), "include_lineage": False, "generate": bool(generate)}
    params = {"generate": "1" if generate else "0"}
    start = time.perf_counter()
    try:
        resp = session.post(url, params=params, json=payload, headers=headers, timeout=float(timeout))
    except Exception as exc:
        return 0, {}, (time.perf_counter() - start) * 1000.0, str(exc)
    latency_ms = (time.perf_counter() - start) * 1000.0
    try:
        body = resp.json()
        if not isinstance(body, dict):
            body = {"raw": body}
    except Exception:
        body = {"raw": (resp.text or "")[:2000]}
    return int(resp.status_code), body, latency_ms, None


def _score_dataset(
    *,
    manifest: dict[str, Any],
    items: Sequence[dict[str, Any]],
    responses: Sequence[dict[str, Any]],
    answer_mode: str,
    semantic_threshold: float,
) -> dict[str, Any]:
    refs = manifest.get("references") if isinstance(manifest.get("references"), Mapping) else None
    reference_sections: set[str] = set()
    if refs:
        sections = refs.get("sections") if isinstance(refs.get("sections"), Mapping) else {}
        for vals in sections.values():
            for sec in (vals or []):
                candidate = str(sec)
                if candidate and not candidate.startswith("EAR-"):
                    candidate = f"EAR-{candidate}"
                norm = _normalize_section_id(candidate)
                if norm:
                    reference_sections.add(norm)

    total = len(items)
    answer_scored = 0
    answer_correct = 0
    label_scored = 0
    label_correct = 0
    unans_total = 0
    unans_correct = 0
    request_422 = 0
    request_503 = 0
    request_failed = 0
    strict_output_failures = 0
    latencies: list[float] = []
    grounded_counts = {
        "items": 0,
        "items_with_citations": 0,
        "total_citations": 0,
        "valid_citations": 0,
        "total_claims": 0,
        "supported_claims": 0,
        "overclaim_count": 0,
        "items_overclaim": 0,
    }
    rows: list[dict[str, Any]] = []

    for item, response in zip(items, responses, strict=True):
        status = int(response.get("status_code") or 0)
        payload = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
        payload = dict(payload or {})
        lat = float(response.get("latency_ms") or 0.0)
        latencies.append(lat)
        if status == 422:
            request_422 += 1
        if status == 503:
            request_503 += 1
        if status >= 400 or status == 0:
            request_failed += 1
        output_ok = bool(payload.get("output_ok"))
        if status == 422 or not output_ok:
            strict_output_failures += 1

        gt = item.get("ground_truth") if isinstance(item.get("ground_truth"), Mapping) else {}
        gt_answer = str(gt.get("answer_text") or "").strip()
        gt_label = str(gt.get("label") or "").strip().lower()
        pred_answer = str(payload.get("answer") or "").strip()
        pred_label = str(payload.get("label") or "").strip().lower()
        if gt_answer:
            answer_scored += 1
            if _answer_ok(gt_answer, pred_answer, answer_mode, semantic_threshold):
                answer_correct += 1
        if gt_label:
            label_scored += 1
            if pred_label == gt_label:
                label_correct += 1
        if gt_label == "unanswerable":
            unans_total += 1
            if pred_label == "unanswerable":
                unans_correct += 1

        cites = payload.get("citations") if isinstance(payload.get("citations"), list) else []
        pred_sections = extract_predicted_sections({"citations": cites})
        gt_sections = extract_ground_truth_sections(item, dataset_refs=refs)
        citation = score_citations(pred_sections, gt_sections)
        grounded = evaluate_groundedness_signals(
            {
                "citations": cites,
                "raw_context": "\n\n".join(str(v) for v in (payload.get("contexts") or [])),
                "retrieved_docs": payload.get("retrieved") or [],
                "answer_text": pred_answer,
                "label": pred_label,
            },
            reference_sections=reference_sections or None,
        )
        counts = grounded.get("counts") if isinstance(grounded.get("counts"), Mapping) else {}
        for key in grounded_counts:
            grounded_counts[key] = int(grounded_counts[key]) + int(counts.get(key) or 0)

        rows.append(
            {
                "id": item.get("id"),
                "status_code": status,
                "latency_ms": lat,
                "output_ok": output_ok,
                "provider": payload.get("provider"),
                "model": payload.get("model"),
                "trace_id": payload.get("trace_id"),
                "label_gold": gt_label,
                "label_predicted": pred_label,
                "label_correct": bool(gt_label and pred_label == gt_label),
                "answer_correct": bool(gt_answer and _answer_ok(gt_answer, pred_answer, answer_mode, semantic_threshold)),
                "citation_precision": citation.precision,
                "citation_recall": citation.recall,
                "citation_f1": citation.f1,
                "groundedness_ok": bool(grounded.get("ok")),
                "error": response.get("error"),
            }
        )

    grounded = finalize_groundedness_metrics(grounded_counts, total)
    return {
        "num_items": total,
        "answer_accuracy": (answer_correct / answer_scored) if answer_scored else 0.0,
        "label_accuracy": (label_correct / label_scored) if label_scored else 0.0,
        "unanswerable_accuracy": (unans_correct / unans_total) if unans_total else 0.0,
        "strict_output_failure_count": strict_output_failures,
        "strict_output_failure_rate": (strict_output_failures / total) if total else 0.0,
        "request_failure_rate": (request_failed / total) if total else 0.0,
        "request_422_count": request_422,
        "request_422_rate": (request_422 / total) if total else 0.0,
        "request_503_count": request_503,
        "request_503_rate": (request_503 / total) if total else 0.0,
        "valid_citation_rate": grounded.get("valid_citation_rate"),
        "supported_rate": grounded.get("supported_rate"),
        "overclaim_rate": grounded.get("overclaim_rate"),
        "latency_ms": {"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
        "items": rows,
    }


def _aggregate(metrics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total_items = sum(int(m.get("num_items") or 0) for m in metrics)
    strict_output_failures = sum(int(m.get("strict_output_failure_count") or 0) for m in metrics)
    request_422 = sum(int(m.get("request_422_count") or 0) for m in metrics)
    request_503 = sum(int(m.get("request_503_count") or 0) for m in metrics)
    weighted = lambda key: sum(float(m.get(key) or 0.0) * int(m.get("num_items") or 0) for m in metrics) / total_items if total_items else 0.0
    all_latencies: list[float] = []
    providers: set[str] = set()
    models: set[str] = set()
    for metric in metrics:
        for row in metric.get("items") or []:
            try:
                all_latencies.append(float(row.get("latency_ms") or 0.0))
            except Exception:
                pass
            if str(row.get("provider") or "").strip():
                providers.add(str(row.get("provider")).strip())
            if str(row.get("model") or "").strip():
                models.add(str(row.get("model")).strip())
    return {
        "num_items": total_items,
        "answer_accuracy": weighted("answer_accuracy"),
        "label_accuracy": weighted("label_accuracy"),
        "unanswerable_accuracy": weighted("unanswerable_accuracy"),
        "strict_output_failure_count": strict_output_failures,
        "strict_output_failure_rate": (strict_output_failures / total_items) if total_items else 0.0,
        "request_422_count": request_422,
        "request_422_rate": (request_422 / total_items) if total_items else 0.0,
        "request_503_count": request_503,
        "request_503_rate": (request_503 / total_items) if total_items else 0.0,
        "valid_citation_rate": weighted("valid_citation_rate"),
        "supported_rate": weighted("supported_rate"),
        "overclaim_rate": weighted("overclaim_rate"),
        "latency_ms": {"p50": _percentile(all_latencies, 0.5), "p95": _percentile(all_latencies, 0.95)},
        "providers": sorted(providers),
        "models": sorted(models),
    }


def _render_summary_md(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Local Adapter Benchmark Summary",
        "",
        f"- Run id: `{summary.get('run_id')}`",
        f"- Created (UTC): `{summary.get('created_at_utc')}`",
        f"- API base URL: `{summary.get('api_base_url')}`",
        f"- Eval manifest digest: `{summary.get('eval_manifest_sha256')}`",
        "",
    ]
    conditions = summary.get("conditions") if isinstance(summary.get("conditions"), Mapping) else {}
    for name in sorted(conditions.keys()):
        metric = conditions.get(name) if isinstance(conditions.get(name), Mapping) else {}
        lat = metric.get("latency_ms") if isinstance(metric.get("latency_ms"), Mapping) else {}
        lines.extend(
            [
                f"## {name}",
                f"- Items: `{metric.get('num_items')}`",
                f"- Answer accuracy: `{float(metric.get('answer_accuracy') or 0.0):.4f}`",
                f"- Label accuracy: `{float(metric.get('label_accuracy') or 0.0):.4f}`",
                f"- Unanswerable accuracy: `{float(metric.get('unanswerable_accuracy') or 0.0):.4f}`",
                f"- Valid citation rate: `{float(metric.get('valid_citation_rate') or 0.0):.4f}`",
                f"- Supported rate: `{float(metric.get('supported_rate') or 0.0):.4f}`",
                f"- Overclaim rate: `{float(metric.get('overclaim_rate') or 0.0):.4f}`",
                f"- Strict-output failure rate: `{float(metric.get('strict_output_failure_rate') or 0.0):.4f}`",
                f"- Request 422 / 503 rates: `{float(metric.get('request_422_rate') or 0.0):.4f}` / `{float(metric.get('request_503_rate') or 0.0):.4f}`",
                f"- Latency p50/p95 ms: `{lat.get('p50')}` / `{lat.get('p95')}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _compute_benchmark_config(
    *,
    run_info: Mapping[str, Any],
    dataset_ids: Sequence[str],
    eval_manifest_path: Path,
    eval_manifest_sha256: str,
    top_k: int,
    answer_score_mode: str,
    semantic_threshold: float,
    timeout_seconds: float,
    require_smoke: bool,
    include_retrieval_control: bool,
    smoke_report_path: Path,
    smoke_report_sha256: str | None,
) -> dict[str, Any]:
    payload = {
        "run_dir": str(run_info.get("run_dir") or ""),
        "training_run_manifest_sha256": str(run_info.get("manifest_sha256") or ""),
        "training_run_metadata_sha256": str(run_info.get("run_metadata_sha256") or ""),
        "training_inference_smoke_sha256": str(run_info.get("inference_smoke_sha256") or ""),
        "dataset_ids": list(dataset_ids),
        "eval_manifest_path": str(eval_manifest_path),
        "eval_manifest_sha256": eval_manifest_sha256,
        "top_k": int(top_k),
        "answer_score_mode": str(answer_score_mode),
        "semantic_threshold": float(semantic_threshold),
        "timeout_seconds": float(timeout_seconds),
        "require_smoke": bool(require_smoke),
        "include_retrieval_control": bool(include_retrieval_control),
        "smoke_report_path": str(smoke_report_path),
        "smoke_report_sha256": smoke_report_sha256,
    }
    payload["config_hash"] = _json_sha256(payload)
    return payload


def _default_run_id(run_info: Mapping[str, Any], config_hash: str) -> str:
    return _safe_name(
        f"benchmark_{Path(str(run_info['run_dir'])).name}_{config_hash[:12]}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark local_adapter /v1/rag/answer and write release-evidence artifacts.")
    parser.add_argument("--run-dir", type=Path, required=True, help="Task 5.3 run directory (dist/training/<run_id>).")
    parser.add_argument("--manifest", type=Path, default=Path("eval") / "manifest.json")
    parser.add_argument("--dataset-id", action="append", dest="dataset_ids", default=None, help="Dataset id (repeatable). Defaults to primary benchmark datasets.")
    parser.add_argument("--base-url", default=os.getenv("EARCRAWLER_API_BASE_URL", "http://127.0.0.1:9001"))
    parser.add_argument("--api-key", default=os.getenv("EARCRAWLER_API_KEY"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--answer-score-mode", choices=["semantic", "normalized", "exact"], default="semantic")
    parser.add_argument("--semantic-threshold", type=float, default=0.6)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--out-root", type=Path, default=Path("dist") / "benchmarks")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--smoke-report", type=Path, default=Path("kg") / "reports" / "local-adapter-smoke.json")
    parser.add_argument("--require-smoke", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-retrieval-control", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        run_info = _assert_run_dir(args.run_dir)
    except Exception as exc:
        print(f"Failed: {exc}")
        return 1

    manifest_path = args.manifest.resolve()
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        print(f"Failed: cannot read manifest {manifest_path}: {exc}")
        return 1
    dataset_ids = list(args.dataset_ids or PRIMARY_DATASETS)
    try:
        ensure_valid_datasets(manifest_path=manifest_path, schema_path=_resolve_schema_path(manifest_path), dataset_ids=dataset_ids)
    except Exception as exc:
        print(f"Failed: dataset validation failed: {exc}")
        return 1

    smoke_payload: dict[str, Any] | None = None
    smoke_copy_path: Path | None = None
    smoke_report_path = args.smoke_report.resolve()
    smoke_report_sha256: str | None = None
    if args.require_smoke:
        try:
            smoke_payload = _load_smoke(smoke_report_path, Path(run_info["run_dir"]))
            smoke_report_sha256 = _sha256_file(smoke_report_path)
        except Exception as exc:
            print(f"Failed: {exc}")
            return 1

    benchmark_config = _compute_benchmark_config(
        run_info=run_info,
        dataset_ids=dataset_ids,
        eval_manifest_path=manifest_path,
        eval_manifest_sha256=_sha256_file(manifest_path),
        top_k=int(args.top_k),
        answer_score_mode=str(args.answer_score_mode),
        semantic_threshold=float(args.semantic_threshold),
        timeout_seconds=float(args.timeout_seconds),
        require_smoke=bool(args.require_smoke),
        include_retrieval_control=bool(args.include_retrieval_control),
        smoke_report_path=smoke_report_path,
        smoke_report_sha256=smoke_report_sha256,
    )

    run_id = _safe_name(args.run_id or _default_run_id(run_info, benchmark_config["config_hash"]))
    out_dir = (args.out_root / run_id).resolve()
    if out_dir.exists() and not args.overwrite:
        print(f"Failed: output directory exists: {out_dir}. Use --overwrite.")
        return 1
    if out_dir.exists() and args.overwrite:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.require_smoke:
        smoke_copy_path = (out_dir / "preconditions" / "local_adapter_smoke.json").resolve()
        _copy_json(smoke_report_path, smoke_copy_path)

    conditions: list[tuple[str, bool]] = [("local_adapter", True)]
    if args.include_retrieval_control:
        conditions.append(("retrieval_only", False))

    started = _utc_now_iso()
    session = requests.Session()
    condition_payloads: dict[str, Any] = {}
    condition_artifact_paths: dict[str, dict[str, str]] = {}
    for condition_name, generate in conditions:
        dataset_metrics: dict[str, Any] = {}
        dataset_paths: dict[str, str] = {}
        for dataset_id in dataset_ids:
            _, dataset_path = _resolve_dataset(manifest, dataset_id, manifest_path)
            rows = sorted(list(_iter_jsonl(dataset_path)), key=lambda item: str(item.get("id") or ""))
            if args.max_items is not None:
                rows = rows[: max(0, int(args.max_items))]
            responses: list[dict[str, Any]] = []
            for row in rows:
                question = str(row.get("question") or "").strip()
                if not question:
                    responses.append({"status_code": 0, "payload": {}, "latency_ms": 0.0, "error": "missing question"})
                    continue
                status, payload, latency, error = _call_answer(
                    session=session,
                    base_url=str(args.base_url),
                    api_key=args.api_key,
                    query=question,
                    top_k=int(args.top_k),
                    generate=generate,
                    timeout=float(args.timeout_seconds),
                )
                if condition_name == "local_adapter" and status == 200:
                    provider = str(payload.get("provider") or "").strip().lower()
                    if provider and provider != "local_adapter":
                        error = f"unexpected provider={provider}"
                responses.append({"status_code": status, "payload": payload, "latency_ms": latency, "error": error})
            metric = _score_dataset(
                manifest=manifest,
                items=rows,
                responses=responses,
                answer_mode=str(args.answer_score_mode),
                semantic_threshold=float(args.semantic_threshold),
            )
            dataset_metrics[dataset_id] = metric
            metric_path = out_dir / "conditions" / condition_name / f"{dataset_id}.json"
            _write_json(metric_path, metric)
            dataset_paths[dataset_id] = str(metric_path)
        condition_payloads[condition_name] = {"datasets": dataset_metrics, "overall": _aggregate(list(dataset_metrics.values()))}
        condition_artifact_paths[condition_name] = dataset_paths

    finished = _utc_now_iso()
    benchmark_summary_path = out_dir / "benchmark_summary.json"
    benchmark_summary_md_path = out_dir / "benchmark_summary.md"
    benchmark_artifacts_path = out_dir / "benchmark_artifacts.json"
    benchmark_manifest_path = out_dir / "benchmark_manifest.json"
    summary = {
        "schema_version": SUMMARY_VERSION,
        "run_id": run_id,
        "created_at_utc": started,
        "finished_at_utc": finished,
        "api_base_url": str(args.base_url),
        "dataset_ids": dataset_ids,
        "top_k": int(args.top_k),
        "answer_score_mode": str(args.answer_score_mode),
        "semantic_threshold": float(args.semantic_threshold),
        "eval_manifest_path": str(manifest_path),
        "eval_manifest_sha256": _sha256_file(manifest_path),
        "benchmark_config": benchmark_config,
        "training_run": run_info,
        "smoke_precondition": {
            "required": bool(args.require_smoke),
            "path": str(smoke_report_path),
            "bundle_copy_path": str(smoke_copy_path) if smoke_copy_path else None,
            "sha256": smoke_report_sha256,
            "bundle_copy_sha256": _sha256_file(smoke_copy_path) if smoke_copy_path and smoke_copy_path.exists() else None,
            "status": str((smoke_payload or {}).get("status") or ""),
        },
        "git": _git_head_dirty(),
        "benchmark_artifacts_path": str(benchmark_artifacts_path),
        "benchmark_manifest_path": str(benchmark_manifest_path),
        "condition_artifact_paths": condition_artifact_paths,
        "conditions": {name: payload.get("overall") for name, payload in sorted(condition_payloads.items())},
    }
    artifacts_payload = {
        "schema_version": SUMMARY_VERSION,
        "run_id": run_id,
        "created_at_utc": started,
        "bundle_root": str(out_dir),
        "training_run": run_info,
        "smoke_precondition": summary["smoke_precondition"],
        "benchmark_config": benchmark_config,
        "condition_artifact_paths": condition_artifact_paths,
        "conditions": condition_payloads,
    }
    _write_json(benchmark_summary_path, summary)
    benchmark_summary_md_path.write_text(_render_summary_md(summary), encoding="utf-8")
    _write_json(benchmark_artifacts_path, artifacts_payload)

    manifest_payload = {
        "manifest_version": SUMMARY_VERSION,
        "run_id": run_id,
        "created_at_utc": started,
        "finished_at_utc": finished,
        "bundle_root": str(out_dir),
        "summary_json": str(benchmark_summary_path),
        "summary_json_sha256": _sha256_file(benchmark_summary_path),
        "summary_md": str(benchmark_summary_md_path),
        "summary_md_sha256": _sha256_file(benchmark_summary_md_path),
        "artifacts_json": str(benchmark_artifacts_path),
        "artifacts_json_sha256": _sha256_file(benchmark_artifacts_path),
        "dataset_ids": dataset_ids,
        "conditions": [name for name, _ in conditions],
        "eval_manifest_path": str(manifest_path),
        "eval_manifest_sha256": _sha256_file(manifest_path),
        "training_run": run_info,
        "smoke_precondition": {
            "required": bool(args.require_smoke),
            "source_path": str(smoke_report_path),
            "bundle_copy_path": str(smoke_copy_path) if smoke_copy_path else None,
            "source_sha256": smoke_report_sha256,
            "bundle_copy_sha256": _sha256_file(smoke_copy_path) if smoke_copy_path and smoke_copy_path.exists() else None,
            "status": str((smoke_payload or {}).get("status") or ""),
        },
        "benchmark_config": benchmark_config,
        "config_hash": benchmark_config["config_hash"],
        "condition_artifact_paths": condition_artifact_paths,
    }
    _write_json(benchmark_manifest_path, manifest_payload)
    print(f"Wrote benchmark bundle: {out_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
