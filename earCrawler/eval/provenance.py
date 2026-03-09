from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Mapping

from earCrawler.rag.retriever import _resolve_backend_name, _resolve_retrieval_mode

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_PREFIXES = (
    "EARCRAWLER_",
    "EAR_",
    "RAG_",
    "KG_",
    "OPENAI_",
    "AZURE_",
    "HF_",
    "TRANSFORMERS_",
    "PYTHONPATH",
)
_SECRET_TOKENS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _truthy(value: object | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _try_run_capture(argv: list[str], *, cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception as exc:
        return 1, str(exc)
    return int(proc.returncode), (proc.stdout or "").strip()


def _git_identity(repo_root: Path) -> dict[str, object]:
    commit_code, commit = _try_run_capture(["git", "rev-parse", "HEAD"], cwd=repo_root)
    branch_code, branch = _try_run_capture(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root
    )
    dirty_code, dirty_status = _try_run_capture(
        ["git", "status", "--porcelain"], cwd=repo_root
    )
    return {
        "commit": commit if commit_code == 0 and commit else "unknown",
        "branch": branch if branch_code == 0 and branch else "unknown",
        "dirty": bool(dirty_code == 0 and dirty_status.splitlines()),
    }


def _display_path(
    value: str | Path | None,
    *,
    repo_root: Path,
    prefer_raw: str | None = None,
) -> str:
    if prefer_raw:
        raw = str(prefer_raw).strip()
        if raw:
            return raw.replace("\\", "/")
    if value is None:
        return ""
    path = Path(value)
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _infer_index_path(index_path: str | Path | None, index_meta_path: str | Path | None) -> Path | None:
    if index_path:
        return Path(index_path)
    if not index_meta_path:
        return None
    meta_path = Path(index_meta_path)
    name = meta_path.name
    if name.endswith(".meta.json"):
        stem = name[: -len(".meta.json")]
        return meta_path.with_name(f"{stem}.faiss")
    return None


def _infer_index_meta_path(index_meta_path: str | Path | None, index_path: str | Path | None) -> Path | None:
    if index_meta_path:
        return Path(index_meta_path)
    if not index_path:
        return None
    return Path(index_path).with_suffix(".meta.json")


def _load_json(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _json_ready(value: object) -> object:
    if isinstance(value, Path):
        return str(value).replace("\\", "/")
    if isinstance(value, Mapping):
        return {str(key): _json_ready(val) for key, val in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _installed_packages_digest() -> str:
    try:
        lines = sorted(
            f"{dist.metadata.get('Name') or getattr(dist, 'name', '')}=={dist.version}"
            for dist in importlib_metadata.distributions()
            if (dist.metadata.get("Name") or getattr(dist, "name", "") or "").strip()
        )
    except Exception as exc:
        lines = [f"error:{type(exc).__name__}:{exc}"]
    return _sha256_text("\n".join(lines))


def _selected_env_vars(env: Mapping[str, str]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key in sorted(env.keys()):
        key_upper = key.upper()
        if not any(key_upper.startswith(prefix) for prefix in _ENV_PREFIXES):
            continue
        value = env[key]
        if any(token in key_upper for token in _SECRET_TOKENS):
            selected[key] = "[REDACTED]"
        else:
            selected[key] = value
    return selected


def _thin_retrieval_snapshot(
    env: Mapping[str, str],
    *,
    enabled: bool | None = None,
    min_docs: int | None = None,
    min_top_score: float | None = None,
    min_total_chars: int | None = None,
) -> dict[str, object]:
    return {
        "enabled": bool(
            enabled
            if enabled is not None
            else _truthy(env.get("EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL"))
        ),
        "min_docs": int(
            min_docs
            if min_docs is not None
            else str(env.get("EARCRAWLER_THIN_RETRIEVAL_MIN_DOCS") or "1")
        ),
        "min_top_score": float(
            min_top_score
            if min_top_score is not None
            else str(env.get("EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE") or "0.0")
        ),
        "min_total_chars": int(
            min_total_chars
            if min_total_chars is not None
            else str(env.get("EARCRAWLER_THIN_RETRIEVAL_MIN_TOTAL_CHARS") or "0")
        ),
    }


def _kg_expansion_snapshot(
    env: Mapping[str, str],
    *,
    enabled: bool | None = None,
    provider: str | None = None,
    failure_policy: str | None = None,
) -> dict[str, object]:
    configured_provider = str(provider or env.get("EARCRAWLER_KG_EXPANSION_PROVIDER") or "").strip()
    if not configured_provider and str(env.get("EARCRAWLER_KG_EXPANSION_PATH") or "").strip():
        configured_provider = "json_stub"
    if not configured_provider:
        configured_provider = "fuseki"
    return {
        "enabled": bool(enabled),
        "provider": configured_provider,
        "failure_policy": str(
            failure_policy or env.get("EARCRAWLER_KG_EXPANSION_FAILURE_POLICY") or "error"
        ).strip()
        or "error",
    }


def build_eval_provenance_snapshot(
    *,
    dataset_id: str,
    dataset_path: str | Path,
    top_k: int,
    strict_output: bool,
    kg_expansion_enabled: bool | None,
    llm_mode: str,
    llm_provider: str | None,
    llm_model: str | None,
    remote_llm_enabled: bool,
    eval_suite: str | None = None,
    thresholds: Mapping[str, object] | None = None,
    manifest_path: Path | None = None,
    run_id: str | None = None,
    corpus_digest: str | None = None,
    index_path: str | Path | None = None,
    index_digest: str | None = None,
    index_meta_path: str | Path | None = None,
    index_meta_digest: str | None = None,
    retrieval_mode: str | None = None,
    retrieval_backend: str | None = None,
    thin_retrieval_enabled: bool | None = None,
    thin_retrieval_min_docs: int | None = None,
    thin_retrieval_min_top_score: float | None = None,
    thin_retrieval_min_total_chars: int | None = None,
    kg_expansion_provider: str | None = None,
    kg_expansion_failure_policy: str | None = None,
    timestamp_utc: str | None = None,
    env: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> dict[str, object]:
    repo = (repo_root or _REPO_ROOT).resolve()
    env_map = dict(os.environ if env is None else env)
    resolved_meta_path = _infer_index_meta_path(index_meta_path, index_path)
    resolved_index_path = _infer_index_path(index_path, resolved_meta_path)
    meta = _load_json(resolved_meta_path)

    meta_corpus_digest = str(meta.get("corpus_digest") or "").strip()
    provided_corpus_digest = str(corpus_digest or "").strip()
    effective_corpus_digest = str(provided_corpus_digest or meta_corpus_digest).strip()
    if (
        meta_corpus_digest
        and provided_corpus_digest
        and provided_corpus_digest != "unknown"
        and meta_corpus_digest != provided_corpus_digest
    ):
        raise ValueError(
            "Index metadata corpus_digest mismatch "
            f"(provenance={provided_corpus_digest}, index_meta={meta_corpus_digest})"
        )
    if not effective_corpus_digest or effective_corpus_digest == "unknown":
        effective_corpus_digest = _sha256_text(
            _canonical_json(
                {
                    "dataset_id": dataset_id,
                    "dataset_path": _display_path(dataset_path, repo_root=repo),
                    "kind": "missing-corpus-digest",
                }
            )
        )

    resolved_index_digest = str(index_digest or _sha256_file(resolved_index_path) or "").strip()
    if not resolved_index_digest:
        resolved_index_digest = _sha256_text(
            _canonical_json(
                {
                    "index_path": _display_path(resolved_index_path, repo_root=repo),
                    "kind": "missing-index-digest",
                }
            )
        )

    resolved_index_meta_digest = str(
        index_meta_digest or _sha256_file(resolved_meta_path) or ""
    ).strip()
    if not resolved_index_meta_digest:
        resolved_index_meta_digest = _sha256_text(
            _canonical_json(
                {
                    "index_meta_path": _display_path(resolved_meta_path, repo_root=repo),
                    "kind": "missing-index-meta-digest",
                }
            )
        )

    index_meta_path_display = _display_path(
        resolved_meta_path or (resolved_index_path.with_suffix(".meta.json") if resolved_index_path else None),
        repo_root=repo,
    )

    resolved_mode = retrieval_mode or _resolve_retrieval_mode()[0]
    resolved_backend = retrieval_backend or _resolve_backend_name()[0]
    llm_mode_value = str(llm_mode or "stubbed").strip().lower() or "stubbed"
    if llm_mode_value not in {"stubbed", "remote"}:
        raise ValueError("llm_mode must be 'stubbed' or 'remote'")

    provider_value = str(llm_provider or "").strip() or "stubbed"
    model_value = str(llm_model or "").strip() or "stubbed"
    if llm_mode_value == "stubbed":
        provider_value = "stubbed"
        model_value = "stubbed"

    snapshot = {
        "run_id": str(run_id or "").strip() or None,
        "git": _git_identity(repo),
        "timestamp_utc": str(timestamp_utc or _utc_now_iso()),
        "dataset_id": str(dataset_id).strip(),
        "dataset_path": _display_path(dataset_path, repo_root=repo),
        "eval_suite": str(eval_suite or dataset_id).strip(),
        "thresholds": _json_ready(thresholds or {}),
        "manifest_path": _display_path(manifest_path, repo_root=repo) if manifest_path else None,
        "corpus_digest": effective_corpus_digest,
        "index_digest": resolved_index_digest,
        "index_meta_digest": resolved_index_meta_digest,
        "index_meta_path": index_meta_path_display,
        "retrieval": {
            "mode": resolved_mode,
            "backend": resolved_backend,
            "fusion": (
                {"algorithm": "rrf", "rrf_k": 60}
                if resolved_mode == "hybrid"
                else None
            ),
            "k": int(top_k),
            "thin_retrieval_refusal": _thin_retrieval_snapshot(
                env_map,
                enabled=thin_retrieval_enabled,
                min_docs=thin_retrieval_min_docs,
                min_top_score=thin_retrieval_min_top_score,
                min_total_chars=thin_retrieval_min_total_chars,
            ),
            "kg_expansion": _kg_expansion_snapshot(
                env_map,
                enabled=kg_expansion_enabled,
                provider=kg_expansion_provider,
                failure_policy=kg_expansion_failure_policy,
            ),
            "strict_output": bool(strict_output),
        },
        "llm": {
            "mode": llm_mode_value,
            "provider": provider_value,
            "model": model_value,
            "remote_llm_enabled": bool(remote_llm_enabled),
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "installed_packages_digest": _installed_packages_digest(),
        "os": {
            "platform": platform.platform(),
        },
        "env": _selected_env_vars(env_map),
    }
    return snapshot


def write_eval_provenance_snapshot(snapshot: Mapping[str, object], *, artifact_root: Path) -> Path:
    artifact_root.mkdir(parents=True, exist_ok=True)
    out_path = artifact_root / "provenance.json"
    out_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


__all__ = [
    "build_eval_provenance_snapshot",
    "write_eval_provenance_snapshot",
]
