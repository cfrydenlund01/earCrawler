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
from urllib.parse import urlsplit

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


def _transport_error_kind(*, status_code: int, error: str | None) -> str | None:
    if int(status_code or 0) != 0:
        return None
    message = str(error or "").strip().lower()
    if not message:
        return "transport_error"
    if "read timed out" in message or "read timeout" in message:
        return "read_timeout"
    if "actively refused" in message or "winerror 10061" in message:
        return "connection_refused"
    if "forcibly closed" in message or "connectionreseterror" in message or "winerror 10054" in message:
        return "connection_reset"
    return "transport_error"


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


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")


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


def _pid_exists(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def _release_run_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            lock_path.unlink()
    except OSError:
        pass


def _acquire_run_lock(
    *,
    lock_path: Path,
    run_id: str,
    out_dir: Path,
    overwrite: bool,
    api_auth_mode: str,
    api_auth_source: str,
) -> dict[str, Any]:
    stale_lock: dict[str, Any] | None = None
    while True:
        if lock_path.exists():
            try:
                existing = _read_json(lock_path)
            except Exception:
                existing = {}
            existing_pid = int(existing.get("pid") or 0)
            existing_out_dir = str(existing.get("out_dir") or "")
            if existing_pid and _pid_exists(existing_pid):
                raise RuntimeError(
                    "Another benchmark process is already active for "
                    f"run_id={run_id!r} at {existing_out_dir or out_dir} "
                    f"(pid={existing_pid}). Inspect its telemetry instead of "
                    "starting a second run."
                )
            stale_lock = {
                "path": str(lock_path),
                "payload": existing,
            }
            _release_run_lock(lock_path)
            continue

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "local-adapter-benchmark-run-lock.v1",
            "run_id": str(run_id),
            "out_dir": str(out_dir),
            "pid": int(os.getpid()),
            "ppid": int(os.getppid()),
            "python_executable": str(sys.executable),
            "cwd": str(Path.cwd()),
            "overwrite": bool(overwrite),
            "api_auth_mode": str(api_auth_mode),
            "api_auth_source": str(api_auth_source),
            "started_at_utc": _utc_now_iso(),
        }
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            _release_run_lock(lock_path)
            raise
        payload["lock_path"] = str(lock_path)
        if stale_lock:
            payload["stale_lock_replaced"] = stale_lock
        return payload


def _benchmark_api_key_label(api_key: str | None) -> str | None:
    raw = str(api_key or "").strip()
    if ":" not in raw:
        return None
    label, _secret = raw.split(":", 1)
    safe = _safe_name(label)
    return safe if safe != "unknown" else None


def _benchmark_api_key_fingerprint(api_key: str | None) -> str | None:
    raw = str(api_key or "").strip()
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _build_auth_precondition(
    *,
    api_key: str | None,
    api_auth_mode: str,
    api_auth_source: str,
    require_authenticated_api: bool,
    required_api_key_label: str | None,
) -> dict[str, Any]:
    key_label = _benchmark_api_key_label(api_key)
    return {
        "required_authenticated_api": bool(require_authenticated_api),
        "required_api_key_label": str(required_api_key_label or "").strip() or None,
        "status": "passed",
        "api_auth_mode": str(api_auth_mode),
        "api_auth_source": str(api_auth_source),
        "api_key_present": bool(api_key),
        "api_key_label": key_label,
        "api_key_fingerprint": _benchmark_api_key_fingerprint(api_key),
    }


def _validate_auth_precondition(
    *,
    api_key: str | None,
    api_auth_mode: str,
    api_auth_source: str,
    require_authenticated_api: bool,
    required_api_key_label: str | None,
) -> dict[str, Any]:
    precondition = _build_auth_precondition(
        api_key=api_key,
        api_auth_mode=api_auth_mode,
        api_auth_source=api_auth_source,
        require_authenticated_api=require_authenticated_api,
        required_api_key_label=required_api_key_label,
    )
    required_label = str(required_api_key_label or "").strip()
    if require_authenticated_api and not api_key:
        precondition["status"] = "failed"
        precondition["error"] = (
            "Authenticated benchmark traffic is required, but no benchmark API "
            "key was resolved."
        )
        return precondition
    if required_label and precondition.get("api_key_label") != required_label:
        precondition["status"] = "failed"
        precondition["error"] = (
            "Resolved benchmark API key label does not match the required "
            f"label {required_label!r}."
        )
        return precondition
    return precondition


def _process_snapshot(command_substring: str) -> list[dict[str, Any]]:
    needle = str(command_substring or "").strip()
    if not needle:
        return []
    script = rf"""
$needle = {json.dumps(needle)}
$rows = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {{ $_.CommandLine -like "*$needle*" }} |
  Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine
if ($rows) {{
  $rows | ConvertTo-Json -Depth 4 -Compress
}}
"""
    try:
        proc = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", script],
            cwd=str(_REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    raw = str(proc.stdout or "").strip()
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except Exception:
        return []
    if isinstance(decoded, dict):
        decoded = [decoded]
    if not isinstance(decoded, list):
        return []
    result: list[dict[str, Any]] = []
    for row in decoded:
        if not isinstance(row, Mapping):
            continue
        result.append(
            {
                "pid": int(row.get("ProcessId") or 0),
                "ppid": int(row.get("ParentProcessId") or 0),
                "name": str(row.get("Name") or ""),
                "created": str(row.get("CreationDate") or ""),
                "command_line": str(row.get("CommandLine") or ""),
            }
        )
    return result


def _capture_transport_diagnostic(
    *,
    diagnostic_path: Path,
    session: requests.Session,
    base_url: str,
    api_key: str | None,
    timeout_seconds: float,
    runtime_state: Mapping[str, Any],
    api_auth_mode: str,
    api_auth_source: str,
    condition: str,
    dataset_id: str,
    item_id: str,
    status_code: int,
    latency_ms: float,
    transport_error: str | None,
    error: str | None,
) -> dict[str, Any]:
    health_ok, health_status, health_error = _probe_health(
        session=session,
        base_url=base_url,
        api_key=api_key,
        timeout=min(5.0, float(timeout_seconds)),
    )
    diagnostic = {
        "schema_version": "local-adapter-benchmark-transport-diagnostic.v1",
        "ts": _utc_now_iso(),
        "run_id": str(runtime_state.get("run_id") or ""),
        "condition": str(condition),
        "dataset_id": str(dataset_id),
        "item_id": str(item_id),
        "status_code": int(status_code or 0),
        "latency_ms": float(latency_ms or 0.0),
        "transport_error": str(transport_error or ""),
        "error": str(error or "") or None,
        "timeout_seconds": float(timeout_seconds),
        "api_auth_mode": str(api_auth_mode),
        "api_auth_source": str(api_auth_source),
        "health_probe": {
            "ok": bool(health_ok),
            "status_code": health_status,
            "error": health_error,
        },
        "runtime_state": {
            "pid": int(runtime_state.get("pid") or 0),
            "ppid": int(runtime_state.get("ppid") or 0),
            "python_executable": str(runtime_state.get("python_executable") or ""),
            "cwd": str(runtime_state.get("cwd") or ""),
            "out_dir": str(runtime_state.get("out_dir") or ""),
            "completed_items": int(runtime_state.get("completed_items") or 0),
            "total_planned_items": int(runtime_state.get("total_planned_items") or 0),
            "current_condition": str(runtime_state.get("current_condition") or ""),
            "current_dataset_id": str(runtime_state.get("current_dataset_id") or ""),
            "current_item_id": str(runtime_state.get("current_item_id") or ""),
            "current_chunk_index": runtime_state.get("current_chunk_index"),
        },
        "matching_benchmark_processes": _process_snapshot("run_local_adapter_benchmark"),
        "matching_run_id_processes": _process_snapshot(str(runtime_state.get("run_id") or "")),
        "api_processes": _process_snapshot("service.api_server.server:app"),
    }
    _append_jsonl(diagnostic_path, diagnostic)
    return {
        "path": str(diagnostic_path.resolve()),
        "health_ok": bool(health_ok),
        "health_status": health_status,
        "health_error": health_error,
    }


def _copy_json(src: Path, dst: Path) -> None:
    _write_json(dst, _read_json(src))


def _emit_runtime_event(
    *,
    event_log_path: Path,
    state_path: Path,
    runtime_state: dict[str, Any],
    event_type: str,
    **details: Any,
) -> None:
    timestamp = _utc_now_iso()
    event_payload: dict[str, Any] = {
        "schema_version": "local-adapter-benchmark-event.v1",
        "ts": timestamp,
        "event": str(event_type),
        "run_id": str(runtime_state.get("run_id") or ""),
        "pid": int(runtime_state.get("pid") or 0),
        "ppid": int(runtime_state.get("ppid") or 0),
    }
    event_payload.update(details)
    _append_jsonl(event_log_path, event_payload)

    runtime_state["updated_at_utc"] = timestamp
    runtime_state["last_event"] = event_payload
    _write_json(state_path, runtime_state)


def _probe_health(
    *,
    session: requests.Session,
    base_url: str,
    api_key: str | None,
    timeout: float,
) -> tuple[bool, int | None, str | None]:
    url = f"{base_url.rstrip('/')}/health"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    try:
        resp = session.get(url, headers=headers, timeout=float(timeout))
    except Exception as exc:
        return False, None, str(exc)
    return int(resp.status_code) == 200, int(resp.status_code), None


def _resolve_api_host_port(base_url: str) -> tuple[str, int]:
    parsed = urlsplit(str(base_url))
    host = parsed.hostname or "127.0.0.1"
    if parsed.port is not None:
        return host, int(parsed.port)
    if parsed.scheme == "https":
        return host, 443
    return host, 80


def _run_repo_command(argv: Sequence[str]) -> tuple[int, str]:
    proc = subprocess.run(
        list(argv),
        cwd=str(_REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return int(proc.returncode), str(proc.stdout or "").strip()


def _restart_api_runtime(
    *,
    base_url: str,
    api_start_script: Path,
    api_stop_script: Path,
) -> dict[str, Any]:
    host, port = _resolve_api_host_port(base_url)
    stop_cmd = ["pwsh", str(api_stop_script.resolve()), "-Port", str(port)]
    start_cmd = [
        "pwsh",
        str(api_start_script.resolve()),
        "-Host",
        host,
        "-Port",
        str(port),
    ]
    stop_rc, stop_output = _run_repo_command(stop_cmd)
    if stop_rc != 0:
        raise RuntimeError(
            f"API stop command failed with exit code {stop_rc}: {stop_output}"
        )
    start_rc, start_output = _run_repo_command(start_cmd)
    if start_rc != 0:
        raise RuntimeError(
            f"API start command failed with exit code {start_rc}: {start_output}"
        )
    return {
        "host": host,
        "port": int(port),
        "api_stop_script": str(api_stop_script.resolve()),
        "api_start_script": str(api_start_script.resolve()),
        "stop_command": stop_cmd,
        "start_command": start_cmd,
        "stop_output": stop_output,
        "start_output": start_output,
        "restarted_at_utc": _utc_now_iso(),
    }


def _resolve_conditions(
    *,
    requested_conditions: Sequence[str] | None,
    include_retrieval_control: bool,
) -> list[tuple[str, bool]]:
    if requested_conditions:
        resolved: list[tuple[str, bool]] = []
        for raw_name in requested_conditions:
            name = str(raw_name or "").strip().lower()
            if not name:
                continue
            if name == "local_adapter":
                resolved.append(("local_adapter", True))
                continue
            if name == "retrieval_only":
                resolved.append(("retrieval_only", False))
                continue
            raise ValueError(f"Unsupported condition: {raw_name!r}")
        if not resolved:
            raise ValueError("At least one valid --condition value is required.")
        deduped: list[tuple[str, bool]] = []
        seen: set[str] = set()
        for name, generate in resolved:
            if name in seen:
                continue
            seen.add(name)
            deduped.append((name, generate))
        return deduped

    conditions: list[tuple[str, bool]] = [("local_adapter", True)]
    if include_retrieval_control:
        conditions.append(("retrieval_only", False))
    return conditions


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


def _warm_local_adapter(
    *,
    session: requests.Session,
    base_url: str,
    api_key: str | None,
    query: str,
    top_k: int,
    timeout: float,
) -> dict[str, Any]:
    status, payload, latency_ms, error = _call_answer(
        session=session,
        base_url=base_url,
        api_key=api_key,
        query=query,
        top_k=top_k,
        generate=True,
        timeout=timeout,
    )
    provider = str(payload.get("provider") or "").strip().lower()
    transport_error = _transport_error_kind(status_code=status, error=error)
    ok = transport_error is None and status in {200, 422}
    if ok and status == 200 and provider and provider != "local_adapter":
        ok = False
        error = f"unexpected provider={provider}"
    return {
        "status": "passed" if ok else "failed",
        "query": query,
        "top_k": int(top_k),
        "timeout_seconds": float(timeout),
        "status_code": status,
        "latency_ms": latency_ms,
        "transport_error": transport_error,
        "error": error,
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "trace_id": payload.get("trace_id"),
        "output_ok": payload.get("output_ok"),
        "output_error": payload.get("output_error"),
    }


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
    transport_failures = 0
    transport_error_kinds: dict[str, int] = {}
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
        error = str(response.get("error") or "").strip() or None
        transport_error = _transport_error_kind(status_code=status, error=error)
        latencies.append(lat)
        if status == 422:
            request_422 += 1
        if status == 503:
            request_503 += 1
        if status >= 400 or status == 0:
            request_failed += 1
        if transport_error:
            transport_failures += 1
            transport_error_kinds[transport_error] = int(transport_error_kinds.get(transport_error) or 0) + 1
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
                "transport_error": transport_error,
                "error": error,
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
        "transport_failure_count": transport_failures,
        "transport_failure_rate": (transport_failures / total) if total else 0.0,
        "transport_error_kinds": transport_error_kinds,
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
    transport_failures = sum(int(m.get("transport_failure_count") or 0) for m in metrics)
    request_422 = sum(int(m.get("request_422_count") or 0) for m in metrics)
    request_503 = sum(int(m.get("request_503_count") or 0) for m in metrics)
    weighted = lambda key: sum(float(m.get(key) or 0.0) * int(m.get("num_items") or 0) for m in metrics) / total_items if total_items else 0.0
    all_latencies: list[float] = []
    providers: set[str] = set()
    models: set[str] = set()
    transport_error_kinds: dict[str, int] = {}
    for metric in metrics:
        for key, value in (metric.get("transport_error_kinds") or {}).items():
            transport_error_kinds[str(key)] = int(transport_error_kinds.get(str(key)) or 0) + int(value or 0)
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
        "transport_failure_count": transport_failures,
        "transport_failure_rate": (transport_failures / total_items) if total_items else 0.0,
        "transport_error_kinds": transport_error_kinds,
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
                f"- Transport failure rate: `{float(metric.get('transport_failure_rate') or 0.0):.4f}`",
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
    local_adapter_warmup: bool,
    local_adapter_warmup_query: str,
    local_adapter_warmup_timeout_seconds: float,
    require_smoke: bool,
    include_retrieval_control: bool,
    condition_names: Sequence[str],
    smoke_report_path: Path,
    smoke_report_sha256: str | None,
    api_auth_mode: str,
    api_auth_source: str,
    chunk_size: int,
    restart_api_between_chunks: bool,
    api_start_script: Path,
    api_stop_script: Path,
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
        "local_adapter_warmup": bool(local_adapter_warmup),
        "local_adapter_warmup_query": str(local_adapter_warmup_query),
        "local_adapter_warmup_timeout_seconds": float(local_adapter_warmup_timeout_seconds),
        "require_smoke": bool(require_smoke),
        "include_retrieval_control": bool(include_retrieval_control),
        "condition_names": list(condition_names),
        "smoke_report_path": str(smoke_report_path),
        "smoke_report_sha256": smoke_report_sha256,
        "api_auth_mode": str(api_auth_mode),
        "api_auth_source": str(api_auth_source),
        "chunk_size": int(chunk_size),
        "restart_api_between_chunks": bool(restart_api_between_chunks),
        "api_start_script": str(api_start_script),
        "api_stop_script": str(api_stop_script),
    }
    payload["config_hash"] = _json_sha256(payload)
    return payload


def _default_run_id(run_info: Mapping[str, Any], config_hash: str) -> str:
    return _safe_name(
        f"benchmark_{Path(str(run_info['run_dir'])).name}_{config_hash[:12]}"
    )


def _resolve_benchmark_api_key(cli_value: str | None) -> tuple[str | None, str]:
    candidate = str(cli_value or "").strip()
    if candidate:
        return candidate, "cli"

    benchmark_env = str(os.getenv("EARCRAWLER_BENCHMARK_API_KEY") or "").strip()
    if benchmark_env:
        return benchmark_env, "env_benchmark_api_key"

    general_env = str(os.getenv("EARCRAWLER_API_KEY") or "").strip()
    if general_env:
        return general_env, "env_api_key"

    return None, "none"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark local_adapter /v1/rag/answer and write release-evidence artifacts.")
    parser.add_argument("--run-dir", type=Path, required=True, help="Task 5.3 run directory (dist/training/<run_id>).")
    parser.add_argument("--manifest", type=Path, default=Path("eval") / "manifest.json")
    parser.add_argument("--dataset-id", action="append", dest="dataset_ids", default=None, help="Dataset id (repeatable). Defaults to primary benchmark datasets.")
    parser.add_argument("--base-url", default=os.getenv("EARCRAWLER_API_BASE_URL", "http://127.0.0.1:9001"))
    parser.add_argument(
        "--api-key",
        default=None,
        help=(
            "Optional X-Api-Key for benchmark traffic. Defaults to "
            "EARCRAWLER_BENCHMARK_API_KEY, then EARCRAWLER_API_KEY."
        ),
    )
    parser.add_argument(
        "--require-authenticated-api",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail before benchmarking unless an API key was resolved.",
    )
    parser.add_argument(
        "--require-api-key-label",
        default=None,
        help="Optional non-secret benchmark key label to require, e.g. benchmark.",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--answer-score-mode", choices=["semantic", "normalized", "exact"], default="semantic")
    parser.add_argument("--semantic-threshold", type=float, default=0.6)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--local-adapter-warmup", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--local-adapter-warmup-query", default="Do laptops to France need a license?")
    parser.add_argument("--local-adapter-warmup-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--out-root", type=Path, default=Path("dist") / "benchmarks")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--smoke-report", type=Path, default=Path("kg") / "reports" / "local-adapter-smoke.json")
    parser.add_argument("--require-smoke", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-retrieval-control", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--condition", action="append", dest="condition_names", choices=["local_adapter", "retrieval_only"], default=None, help="Condition to run (repeatable). Defaults to local_adapter and retrieval_only when --include-retrieval-control is enabled.")
    parser.add_argument("--chunk-size", type=int, default=0)
    parser.add_argument("--restart-api-between-chunks", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--api-start-script", type=Path, default=Path("scripts") / "api-start.ps1")
    parser.add_argument("--api-stop-script", type=Path, default=Path("scripts") / "api-stop.ps1")
    parser.add_argument("--max-consecutive-transport-failures", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    api_key, api_key_source = _resolve_benchmark_api_key(args.api_key)
    api_auth_mode = "authenticated" if api_key else "anonymous"

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

    try:
        conditions = _resolve_conditions(
            requested_conditions=args.condition_names,
            include_retrieval_control=bool(args.include_retrieval_control),
        )
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
        local_adapter_warmup=bool(args.local_adapter_warmup),
        local_adapter_warmup_query=str(args.local_adapter_warmup_query),
        local_adapter_warmup_timeout_seconds=float(args.local_adapter_warmup_timeout_seconds),
        require_smoke=bool(args.require_smoke),
        include_retrieval_control=bool(args.include_retrieval_control),
        condition_names=[name for name, _ in conditions],
        smoke_report_path=smoke_report_path,
        smoke_report_sha256=smoke_report_sha256,
        api_auth_mode=api_auth_mode,
        api_auth_source=api_key_source,
        chunk_size=max(0, int(args.chunk_size)),
        restart_api_between_chunks=bool(args.restart_api_between_chunks),
        api_start_script=args.api_start_script.resolve(),
        api_stop_script=args.api_stop_script.resolve(),
    )

    run_id = _safe_name(args.run_id or _default_run_id(run_info, benchmark_config["config_hash"]))
    out_dir = (args.out_root / run_id).resolve()
    auth_precondition = _validate_auth_precondition(
        api_key=api_key,
        api_auth_mode=api_auth_mode,
        api_auth_source=api_key_source,
        require_authenticated_api=bool(args.require_authenticated_api),
        required_api_key_label=str(args.require_api_key_label or "").strip() or None,
    )
    if str(auth_precondition.get("status") or "") != "passed":
        print(f"Failed: {auth_precondition.get('error')}")
        return 1
    lock_path = (args.out_root / ".locks" / f"{run_id}.lock.json").resolve()
    try:
        run_lock = _acquire_run_lock(
            lock_path=lock_path,
            run_id=run_id,
            out_dir=out_dir,
            overwrite=bool(args.overwrite),
            api_auth_mode=api_auth_mode,
            api_auth_source=api_key_source,
        )
    except Exception as exc:
        print(f"Failed: {exc}")
        return 1
    if out_dir.exists() and not args.overwrite:
        _release_run_lock(lock_path)
        print(f"Failed: output directory exists: {out_dir}. Use --overwrite.")
        return 1
    if out_dir.exists() and args.overwrite:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if True:
        if args.require_smoke:
            smoke_copy_path = (out_dir / "preconditions" / "local_adapter_smoke.json").resolve()
            _copy_json(smoke_report_path, smoke_copy_path)
        auth_precondition_path = (out_dir / "preconditions" / "benchmark_api_auth.json").resolve()
        _write_json(auth_precondition_path, auth_precondition)
        dataset_row_counts: dict[str, int] = {}
        for dataset_id in dataset_ids:
            _, dataset_path = _resolve_dataset(manifest, dataset_id, manifest_path)
            row_count = len(list(_iter_jsonl(dataset_path)))
            if args.max_items is not None:
                row_count = min(row_count, max(0, int(args.max_items)))
            dataset_row_counts[dataset_id] = row_count

        started = _utc_now_iso()
        session = requests.Session()
        telemetry_dir = (out_dir / "telemetry").resolve()
        event_log_path = telemetry_dir / "benchmark_events.jsonl"
        state_path = telemetry_dir / "benchmark_state.json"
        transport_diag_path = telemetry_dir / "transport_diagnostics.jsonl"
        total_planned_items = sum(dataset_row_counts.values()) * len(conditions)
        runtime_state: dict[str, Any] = {
            "schema_version": "local-adapter-benchmark-state.v1",
            "run_id": run_id,
            "status": "running",
            "started_at_utc": started,
            "updated_at_utc": started,
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "out_dir": str(out_dir),
            "event_log_path": str(event_log_path),
            "transport_diagnostics_path": str(transport_diag_path),
            "run_lock_path": str(lock_path),
            "condition_names": [name for name, _ in conditions],
            "dataset_ids": list(dataset_ids),
            "total_planned_items": int(total_planned_items),
            "completed_items": 0,
            "current_condition": None,
            "current_dataset_id": None,
            "current_item_id": None,
            "current_chunk_index": None,
        }
    _emit_runtime_event(
        event_log_path=event_log_path,
        state_path=state_path,
        runtime_state=runtime_state,
        event_type="run_started",
        base_url=str(args.base_url),
        timeout_seconds=float(args.timeout_seconds),
        max_items=args.max_items,
        condition_names=[name for name, _ in conditions],
        api_auth_mode=api_auth_mode,
        api_auth_source=api_key_source,
        require_smoke=bool(args.require_smoke),
        local_adapter_warmup=bool(args.local_adapter_warmup),
        auth_precondition_path=str(auth_precondition_path),
        run_lock_path=str(lock_path),
    )
    _emit_runtime_event(
        event_log_path=event_log_path,
        state_path=state_path,
        runtime_state=runtime_state,
        event_type="auth_precondition_checked",
        auth_precondition_path=str(auth_precondition_path),
        api_auth_mode=api_auth_mode,
        api_auth_source=api_key_source,
        api_key_label=auth_precondition.get("api_key_label"),
        api_key_fingerprint=auth_precondition.get("api_key_fingerprint"),
        required_authenticated_api=bool(args.require_authenticated_api),
    )
    _emit_runtime_event(
        event_log_path=event_log_path,
        state_path=state_path,
        runtime_state=runtime_state,
        event_type="run_lock_acquired",
        run_lock_path=str(lock_path),
        stale_lock_replaced=run_lock.get("stale_lock_replaced"),
    )
    if smoke_copy_path:
        _emit_runtime_event(
            event_log_path=event_log_path,
            state_path=state_path,
            runtime_state=runtime_state,
            event_type="smoke_precondition_copied",
            smoke_copy_path=str(smoke_copy_path),
            smoke_report_sha256=smoke_report_sha256,
        )
    warmup_path: Path | None = None
    warmup_result: dict[str, Any] | None = None
    if bool(args.local_adapter_warmup):
        warmup_result = _warm_local_adapter(
            session=session,
            base_url=str(args.base_url),
            api_key=api_key,
            query=str(args.local_adapter_warmup_query),
            top_k=max(1, min(int(args.top_k), 3)),
            timeout=float(args.local_adapter_warmup_timeout_seconds),
        )
        warmup_path = (out_dir / "preconditions" / "local_adapter_warmup.json").resolve()
        _write_json(warmup_path, warmup_result)
        _emit_runtime_event(
            event_log_path=event_log_path,
            state_path=state_path,
            runtime_state=runtime_state,
            event_type="warmup_completed",
            warmup_path=str(warmup_path),
            warmup_status=str(warmup_result.get("status") or ""),
            status_code=warmup_result.get("status_code"),
            latency_ms=warmup_result.get("latency_ms"),
            transport_error=warmup_result.get("transport_error"),
            provider=warmup_result.get("provider"),
            model=warmup_result.get("model"),
            trace_id=warmup_result.get("trace_id"),
            output_ok=warmup_result.get("output_ok"),
            output_error=warmup_result.get("output_error"),
        )
        if str(warmup_result.get("status") or "") != "passed":
            health_ok, health_status, health_error = _probe_health(
                session=session,
                base_url=str(args.base_url),
                api_key=api_key,
                timeout=min(5.0, float(args.timeout_seconds)),
            )
            failure_payload = {
                "schema_version": SUMMARY_VERSION,
                "status": "warmup_failed",
                "run_id": run_id,
                "condition": "local_adapter",
                "warmup": warmup_result,
                "health_probe": {
                    "ok": health_ok,
                    "status_code": health_status,
                    "error": health_error,
                },
            }
            _write_json(out_dir / "benchmark_failure.json", failure_payload)
            runtime_state["status"] = "failed"
            _emit_runtime_event(
                event_log_path=event_log_path,
                state_path=state_path,
                runtime_state=runtime_state,
                event_type="run_failed",
                failure_status="warmup_failed",
                failure_path=str((out_dir / "benchmark_failure.json").resolve()),
                status_code=warmup_result.get("status_code"),
                transport_error=warmup_result.get("transport_error"),
                error=warmup_result.get("error"),
                health_ok=health_ok,
                health_status=health_status,
                health_error=health_error,
            )
            print(
                "Failed: local-adapter warmup failed before scoring; "
                f"status={warmup_result.get('status_code')!r} "
                f"transport_error={warmup_result.get('transport_error')!r} "
                f"error={warmup_result.get('error')!r}"
            )
            return 1
    condition_payloads: dict[str, Any] = {}
    condition_artifact_paths: dict[str, dict[str, str]] = {}
    chunk_restart_events: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for condition_name, generate in conditions:
        runtime_state["current_condition"] = condition_name
        runtime_state["current_dataset_id"] = None
        runtime_state["current_item_id"] = None
        runtime_state["current_chunk_index"] = None
        _emit_runtime_event(
            event_log_path=event_log_path,
            state_path=state_path,
            runtime_state=runtime_state,
            event_type="condition_started",
            condition=condition_name,
            generate=bool(generate),
        )
        dataset_metrics: dict[str, Any] = {}
        dataset_paths: dict[str, str] = {}
        dataset_chunk_events: dict[str, list[dict[str, Any]]] = {}
        for dataset_id in dataset_ids:
            consecutive_transport_failures = 0
            _, dataset_path = _resolve_dataset(manifest, dataset_id, manifest_path)
            rows = sorted(list(_iter_jsonl(dataset_path)), key=lambda item: str(item.get("id") or ""))
            if args.max_items is not None:
                rows = rows[: max(0, int(args.max_items))]
            runtime_state["current_dataset_id"] = dataset_id
            runtime_state["current_item_id"] = None
            runtime_state["current_chunk_index"] = None
            _emit_runtime_event(
                event_log_path=event_log_path,
                state_path=state_path,
                runtime_state=runtime_state,
                event_type="dataset_started",
                condition=condition_name,
                dataset_id=dataset_id,
                dataset_path=str(dataset_path),
                num_rows=len(rows),
            )
            responses: list[dict[str, Any]] = []
            chunk_size = max(0, int(args.chunk_size))
            chunks: list[Sequence[dict[str, Any]]]
            if chunk_size > 0:
                chunks = [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)]
            else:
                chunks = [rows]
            restart_events: list[dict[str, Any]] = []
            for chunk_index, chunk_rows in enumerate(chunks):
                runtime_state["current_chunk_index"] = chunk_index + 1
                _emit_runtime_event(
                    event_log_path=event_log_path,
                    state_path=state_path,
                    runtime_state=runtime_state,
                    event_type="chunk_started",
                    condition=condition_name,
                    dataset_id=dataset_id,
                    chunk_index=chunk_index + 1,
                    chunk_size=len(chunk_rows),
                )
                if (
                    chunk_index > 0
                    and condition_name == "local_adapter"
                    and bool(args.restart_api_between_chunks)
                ):
                    try:
                        restart_event = _restart_api_runtime(
                            base_url=str(args.base_url),
                            api_start_script=args.api_start_script,
                            api_stop_script=args.api_stop_script,
                        )
                    except Exception as exc:
                        failure_payload = {
                            "schema_version": SUMMARY_VERSION,
                            "status": "api_restart_failed",
                            "run_id": run_id,
                            "condition": condition_name,
                            "dataset_id": dataset_id,
                            "chunk_index": chunk_index + 1,
                            "processed_items": len(responses),
                            "error": str(exc),
                        }
                        _write_json(out_dir / "benchmark_failure.json", failure_payload)
                        runtime_state["status"] = "failed"
                        _emit_runtime_event(
                            event_log_path=event_log_path,
                            state_path=state_path,
                            runtime_state=runtime_state,
                            event_type="run_failed",
                            failure_status="api_restart_failed",
                            failure_path=str((out_dir / "benchmark_failure.json").resolve()),
                            condition=condition_name,
                            dataset_id=dataset_id,
                            chunk_index=chunk_index + 1,
                            error=str(exc),
                        )
                        print(
                            "Failed: benchmark could not restart the API before "
                            f"{condition_name}/{dataset_id} chunk {chunk_index + 1}: {exc}"
                        )
                        _release_run_lock(lock_path)
                        return 1
                    session.close()
                    session = requests.Session()
                    if bool(args.local_adapter_warmup):
                        chunk_warmup = _warm_local_adapter(
                            session=session,
                            base_url=str(args.base_url),
                            api_key=api_key,
                            query=str(args.local_adapter_warmup_query),
                            top_k=max(1, min(int(args.top_k), 3)),
                            timeout=float(args.local_adapter_warmup_timeout_seconds),
                        )
                        restart_event["warmup"] = chunk_warmup
                        if str(chunk_warmup.get("status") or "") != "passed":
                            health_ok, health_status, health_error = _probe_health(
                                session=session,
                                base_url=str(args.base_url),
                                api_key=api_key,
                                timeout=min(5.0, float(args.timeout_seconds)),
                            )
                            failure_payload = {
                                "schema_version": SUMMARY_VERSION,
                                "status": "chunk_warmup_failed",
                                "run_id": run_id,
                                "condition": condition_name,
                                "dataset_id": dataset_id,
                                "chunk_index": chunk_index + 1,
                                "processed_items": len(responses),
                                "restart_event": restart_event,
                                "health_probe": {
                                    "ok": health_ok,
                                    "status_code": health_status,
                                    "error": health_error,
                                },
                            }
                            _write_json(out_dir / "benchmark_failure.json", failure_payload)
                            runtime_state["status"] = "failed"
                            _emit_runtime_event(
                                event_log_path=event_log_path,
                                state_path=state_path,
                                runtime_state=runtime_state,
                                event_type="run_failed",
                                failure_status="chunk_warmup_failed",
                                failure_path=str((out_dir / "benchmark_failure.json").resolve()),
                                condition=condition_name,
                                dataset_id=dataset_id,
                                chunk_index=chunk_index + 1,
                                status_code=chunk_warmup.get("status_code"),
                                transport_error=chunk_warmup.get("transport_error"),
                                health_ok=health_ok,
                                health_status=health_status,
                                health_error=health_error,
                            )
                            print(
                                "Failed: local-adapter warmup failed after API restart before "
                                f"{condition_name}/{dataset_id} chunk {chunk_index + 1}; "
                                f"status={chunk_warmup.get('status_code')!r} "
                                f"transport_error={chunk_warmup.get('transport_error')!r}"
                            )
                            _release_run_lock(lock_path)
                            return 1
                    restart_events.append(restart_event)

                for row_index, row in enumerate(chunk_rows, start=1):
                    item_id = str(row.get("id") or f"{dataset_id}:{len(responses) + 1}")
                    question = str(row.get("question") or "").strip()
                    runtime_state["current_item_id"] = item_id
                    _emit_runtime_event(
                        event_log_path=event_log_path,
                        state_path=state_path,
                        runtime_state=runtime_state,
                        event_type="item_started",
                        condition=condition_name,
                        dataset_id=dataset_id,
                        chunk_index=chunk_index + 1,
                        chunk_row_index=row_index,
                        item_id=item_id,
                        question=question,
                        question_length=len(question),
                        generate=bool(generate),
                    )
                    question = str(row.get("question") or "").strip()
                    if not question:
                        responses.append({"status_code": 0, "payload": {}, "latency_ms": 0.0, "error": "missing question"})
                        runtime_state["completed_items"] = int(runtime_state.get("completed_items") or 0) + 1
                        _emit_runtime_event(
                            event_log_path=event_log_path,
                            state_path=state_path,
                            runtime_state=runtime_state,
                            event_type="item_completed",
                            condition=condition_name,
                            dataset_id=dataset_id,
                            chunk_index=chunk_index + 1,
                            item_id=item_id,
                            status_code=0,
                            latency_ms=0.0,
                            transport_error="transport_error",
                            error="missing question",
                        )
                        continue
                    status, payload, latency, error = _call_answer(
                        session=session,
                        base_url=str(args.base_url),
                        api_key=api_key,
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
                    transport_error = _transport_error_kind(status_code=status, error=error)
                    runtime_state["completed_items"] = int(runtime_state.get("completed_items") or 0) + 1
                    _emit_runtime_event(
                        event_log_path=event_log_path,
                        state_path=state_path,
                        runtime_state=runtime_state,
                        event_type="item_completed",
                        condition=condition_name,
                        dataset_id=dataset_id,
                        chunk_index=chunk_index + 1,
                        item_id=item_id,
                        status_code=status,
                        latency_ms=latency,
                        transport_error=transport_error,
                        error=error,
                        trace_id=payload.get("trace_id"),
                        provider=payload.get("provider"),
                        model=payload.get("model"),
                        output_ok=payload.get("output_ok"),
                    )
                    if transport_error:
                        diagnostic = _capture_transport_diagnostic(
                            diagnostic_path=transport_diag_path,
                            session=session,
                            base_url=str(args.base_url),
                            api_key=api_key,
                            timeout_seconds=float(args.timeout_seconds),
                            runtime_state=runtime_state,
                            api_auth_mode=api_auth_mode,
                            api_auth_source=api_key_source,
                            condition=condition_name,
                            dataset_id=dataset_id,
                            item_id=item_id,
                            status_code=status,
                            latency_ms=latency,
                            transport_error=transport_error,
                            error=error,
                        )
                        _emit_runtime_event(
                            event_log_path=event_log_path,
                            state_path=state_path,
                            runtime_state=runtime_state,
                            event_type="transport_diagnostic_captured",
                            condition=condition_name,
                            dataset_id=dataset_id,
                            item_id=item_id,
                            transport_error=transport_error,
                            diagnostic_path=diagnostic["path"],
                            health_ok=diagnostic["health_ok"],
                            health_status=diagnostic["health_status"],
                            health_error=diagnostic["health_error"],
                        )
                    if transport_error:
                        consecutive_transport_failures += 1
                    else:
                        consecutive_transport_failures = 0
                    max_consecutive = max(0, int(args.max_consecutive_transport_failures))
                    if max_consecutive and consecutive_transport_failures >= max_consecutive:
                        health_ok, health_status, health_error = _probe_health(
                            session=session,
                            base_url=str(args.base_url),
                            api_key=api_key,
                            timeout=min(5.0, float(args.timeout_seconds)),
                        )
                        failure_payload = {
                            "schema_version": SUMMARY_VERSION,
                            "status": "aborted_transport_failure",
                            "run_id": run_id,
                            "condition": condition_name,
                            "dataset_id": dataset_id,
                            "processed_items": len(responses),
                            "consecutive_transport_failures": consecutive_transport_failures,
                            "max_consecutive_transport_failures": max_consecutive,
                            "transport_error": transport_error,
                            "last_error": error,
                            "transport_diagnostics_path": str(transport_diag_path.resolve()),
                            "health_probe": {
                                "ok": health_ok,
                                "status_code": health_status,
                                "error": health_error,
                            },
                        }
                        _write_json(out_dir / "benchmark_failure.json", failure_payload)
                        runtime_state["status"] = "failed"
                        _emit_runtime_event(
                            event_log_path=event_log_path,
                            state_path=state_path,
                            runtime_state=runtime_state,
                            event_type="run_failed",
                            failure_status="aborted_transport_failure",
                            failure_path=str((out_dir / "benchmark_failure.json").resolve()),
                            condition=condition_name,
                            dataset_id=dataset_id,
                            processed_items=len(responses),
                            consecutive_transport_failures=consecutive_transport_failures,
                            transport_error=transport_error,
                            last_error=error,
                            health_ok=health_ok,
                            health_status=health_status,
                            health_error=health_error,
                        )
                        print(
                            "Failed: aborting benchmark after "
                            f"{consecutive_transport_failures} consecutive transport failures "
                            f"for {condition_name}/{dataset_id}; last_error={error!r}; "
                            f"health_ok={health_ok} status={health_status!r}"
                        )
                        _release_run_lock(lock_path)
                        return 1
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
            _emit_runtime_event(
                event_log_path=event_log_path,
                state_path=state_path,
                runtime_state=runtime_state,
                event_type="dataset_completed",
                condition=condition_name,
                dataset_id=dataset_id,
                metric_path=str(metric_path.resolve()),
                num_items=metric.get("num_items"),
                transport_failure_count=metric.get("transport_failure_count"),
                request_422_count=metric.get("request_422_count"),
                request_503_count=metric.get("request_503_count"),
            )
            if restart_events:
                dataset_chunk_events[dataset_id] = restart_events
        condition_payloads[condition_name] = {"datasets": dataset_metrics, "overall": _aggregate(list(dataset_metrics.values()))}
        condition_artifact_paths[condition_name] = dataset_paths
        _emit_runtime_event(
            event_log_path=event_log_path,
            state_path=state_path,
            runtime_state=runtime_state,
            event_type="condition_completed",
            condition=condition_name,
            overall=condition_payloads[condition_name]["overall"],
        )
        if dataset_chunk_events:
            chunk_restart_events[condition_name] = dataset_chunk_events

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
        "auth_precondition": auth_precondition,
        "warmup_precondition": {
            "required": bool(args.local_adapter_warmup),
            "path": str(warmup_path) if warmup_path else None,
            "status": str((warmup_result or {}).get("status") or ""),
            "status_code": (warmup_result or {}).get("status_code"),
            "transport_error": (warmup_result or {}).get("transport_error"),
            "provider": (warmup_result or {}).get("provider"),
            "model": (warmup_result or {}).get("model"),
            "trace_id": (warmup_result or {}).get("trace_id"),
        },
        "git": _git_head_dirty(),
        "benchmark_artifacts_path": str(benchmark_artifacts_path),
        "benchmark_manifest_path": str(benchmark_manifest_path),
        "telemetry": {
            "event_log_path": str(event_log_path),
            "state_path": str(state_path),
            "transport_diagnostics_path": str(transport_diag_path),
        },
        "run_lock": {
            "path": str(lock_path),
        },
        "condition_artifact_paths": condition_artifact_paths,
        "chunk_restart_events": chunk_restart_events,
        "conditions": {name: payload.get("overall") for name, payload in sorted(condition_payloads.items())},
    }
    artifacts_payload = {
        "schema_version": SUMMARY_VERSION,
        "run_id": run_id,
        "created_at_utc": started,
        "bundle_root": str(out_dir),
        "training_run": run_info,
        "smoke_precondition": summary["smoke_precondition"],
        "auth_precondition": summary["auth_precondition"],
        "warmup_precondition": summary["warmup_precondition"],
        "benchmark_config": benchmark_config,
        "telemetry": summary["telemetry"],
        "run_lock": summary["run_lock"],
        "condition_artifact_paths": condition_artifact_paths,
        "chunk_restart_events": chunk_restart_events,
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
        "auth_precondition": {
            "path": str(auth_precondition_path),
            "sha256": _sha256_file(auth_precondition_path),
            "status": str(auth_precondition.get("status") or ""),
            "api_auth_mode": str(auth_precondition.get("api_auth_mode") or ""),
            "api_auth_source": str(auth_precondition.get("api_auth_source") or ""),
            "api_key_label": auth_precondition.get("api_key_label"),
            "api_key_fingerprint": auth_precondition.get("api_key_fingerprint"),
        },
        "warmup_precondition": {
            "required": bool(args.local_adapter_warmup),
            "path": str(warmup_path) if warmup_path else None,
            "sha256": _sha256_file(warmup_path) if warmup_path and warmup_path.exists() else None,
            "status": str((warmup_result or {}).get("status") or ""),
            "status_code": (warmup_result or {}).get("status_code"),
            "transport_error": (warmup_result or {}).get("transport_error"),
        },
        "benchmark_config": benchmark_config,
        "config_hash": benchmark_config["config_hash"],
        "telemetry": summary["telemetry"],
        "condition_artifact_paths": condition_artifact_paths,
        "chunk_restart_events": chunk_restart_events,
    }
    _write_json(benchmark_manifest_path, manifest_payload)
    runtime_state["status"] = "completed"
    runtime_state["current_condition"] = None
    runtime_state["current_dataset_id"] = None
    runtime_state["current_item_id"] = None
    runtime_state["current_chunk_index"] = None
    _emit_runtime_event(
        event_log_path=event_log_path,
        state_path=state_path,
        runtime_state=runtime_state,
        event_type="run_completed",
        summary_path=str(benchmark_summary_path.resolve()),
        manifest_path=str(benchmark_manifest_path.resolve()),
        total_conditions=len(conditions),
        total_completed_items=runtime_state.get("completed_items"),
    )
    print(f"Wrote benchmark bundle: {out_dir}")
    _release_run_lock(lock_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
