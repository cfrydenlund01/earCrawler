from __future__ import annotations

"""Deterministic corpus -> FAISS index rebuild helpers."""

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from earCrawler.rag import pipeline as rag_pipeline
from earCrawler.rag.build_corpus import compute_corpus_digest
from earCrawler.rag.corpus_contract import (
    load_corpus_jsonl,
    normalize_ear_section_id,
    require_valid_corpus,
)
from earCrawler.rag.index_builder import INDEX_META_VERSION, build_faiss_index_from_corpus
from earCrawler.rag.offline_snapshot_manifest import compute_sha256_hex
from earCrawler.rag.retriever import describe_retriever_config


INDEX_BUILD_LOG_VERSION = "retrieval-index-build.v1"


@dataclass(frozen=True)
class SnapshotIndexBundle:
    snapshot_id: str
    index_dir: Path
    index_path: Path
    meta_path: Path
    build_log_path: Path
    env_file_path: Path
    env_ps1_path: Path
    embedding_model: str
    corpus_digest: str
    doc_count: int
    build_timestamp_utc: str
    smoke_result_count: int
    smoke_expected_hits: int


def _parse_iso8601_utc(value: str) -> None:
    normalized = value.replace("Z", "+00:00")
    datetime.fromisoformat(normalized)


def _resolve_snapshot_id(docs: Sequence[Mapping[str, Any]], corpus_path: Path) -> str:
    snapshot_ids = {
        str(doc.get("snapshot_id") or "").strip()
        for doc in docs
        if isinstance(doc.get("snapshot_id"), str) and str(doc.get("snapshot_id")).strip()
    }
    if len(snapshot_ids) == 1:
        return next(iter(snapshot_ids))
    if len(snapshot_ids) > 1:
        raise ValueError(
            "Corpus contains multiple snapshot_id values: " + ", ".join(sorted(snapshot_ids))
        )
    parent_name = corpus_path.parent.name.strip()
    if parent_name:
        return parent_name
    raise ValueError("Unable to resolve snapshot_id from corpus metadata or path")


def _read_meta(meta_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid index metadata JSON: {meta_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Index metadata must be an object: {meta_path}")
    return payload


def _verify_meta_contract(
    meta: Mapping[str, Any],
    *,
    expected_model: str,
    expected_digest: str,
    expected_doc_count: int,
) -> str:
    if str(meta.get("schema_version") or "") != INDEX_META_VERSION:
        raise ValueError(
            f"Index metadata schema_version must be '{INDEX_META_VERSION}'"
        )
    ts = str(meta.get("build_timestamp_utc") or "").strip()
    if not ts:
        raise ValueError("Index metadata missing required field 'build_timestamp_utc'")
    try:
        _parse_iso8601_utc(ts)
    except Exception as exc:
        raise ValueError(f"Invalid build_timestamp_utc in index metadata: {ts}") from exc

    if str(meta.get("embedding_model") or "") != expected_model:
        raise ValueError(
            f"Index metadata embedding_model mismatch (expected '{expected_model}', got '{meta.get('embedding_model')}')"
        )
    if str(meta.get("corpus_digest") or "") != expected_digest:
        raise ValueError(
            f"Index metadata corpus_digest mismatch (expected '{expected_digest}', got '{meta.get('corpus_digest')}')"
        )

    doc_count = meta.get("doc_count")
    if not isinstance(doc_count, int):
        raise ValueError("Index metadata doc_count must be an integer")
    if doc_count != expected_doc_count:
        raise ValueError(
            f"Index metadata doc_count mismatch (expected {expected_doc_count}, got {doc_count})"
        )

    rows = meta.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Index metadata rows must be a list")
    if len(rows) != expected_doc_count:
        raise ValueError(
            f"Index metadata rows length mismatch (expected {expected_doc_count}, got {len(rows)})"
        )
    return ts


def _write_runtime_env_files(index_dir: Path, *, index_path: Path, model_name: str) -> tuple[Path, Path]:
    env_file = index_dir / "runtime.env"
    env_ps1 = index_dir / "runtime_env.ps1"
    index_value = str(index_path.resolve())

    env_file.write_text(
        "EARCRAWLER_FAISS_INDEX=" + index_value + "\n"
        "EARCRAWLER_FAISS_MODEL=" + model_name + "\n",
        encoding="utf-8",
        newline="\n",
    )
    env_ps1.write_text(
        f'$env:EARCRAWLER_FAISS_INDEX="{index_value}"\n'
        f'$env:EARCRAWLER_FAISS_MODEL="{model_name}"\n',
        encoding="utf-8",
        newline="\n",
    )
    return env_file, env_ps1


def _with_temp_env(env: Mapping[str, str]):
    class _EnvGuard:
        def __enter__(self):
            self._prior: dict[str, str | None] = {}
            for key, value in env.items():
                self._prior[key] = os.environ.get(key)
                os.environ[key] = value
            return self

        def __exit__(self, exc_type, exc, tb):
            for key, old in self._prior.items():
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old

    return _EnvGuard()


def _verify_pipeline_env_wiring(*, index_path: Path, model_name: str):
    env = {
        "EARCRAWLER_FAISS_INDEX": str(index_path.resolve()),
        "EARCRAWLER_FAISS_MODEL": model_name,
    }
    warnings: list[dict[str, object]] = []
    with _with_temp_env(env):
        retriever = rag_pipeline._ensure_retriever(None, strict=True, warnings=warnings)
        cfg = describe_retriever_config(retriever)
    configured_index = Path(str(cfg.get("index_path") or ""))
    if configured_index.resolve() != index_path.resolve():
        raise ValueError(
            f"Pipeline env wiring mismatch for index path (expected {index_path}, got {configured_index})"
        )
    if str(cfg.get("model_name") or "") != model_name:
        raise ValueError(
            f"Pipeline env wiring mismatch for model (expected {model_name}, got {cfg.get('model_name')})"
        )
    return retriever, cfg


def _run_retrieval_smoke(
    *,
    retriever: object,
    query: str,
    top_k: int,
    expected_sections: Sequence[str] | None = None,
) -> tuple[int, int, list[dict[str, Any]]]:
    docs = rag_pipeline.retrieve_regulation_context(
        query,
        top_k=top_k,
        retriever=retriever,
        strict=True,
        warnings=[],
    )
    if not docs:
        raise ValueError("Retrieval smoke check returned no results")

    valid: list[dict[str, Any]] = []
    for doc in docs:
        section_id = str(doc.get("section_id") or "").strip()
        text = str(doc.get("text") or "").strip()
        if section_id and text:
            valid.append(doc)
    if not valid:
        raise ValueError(
            "Retrieval smoke check returned results, but none had non-empty section_id and text"
        )

    expected_canonical = {
        norm
        for norm in (normalize_ear_section_id(value) for value in (expected_sections or []))
        if norm
    }
    matched = 0
    if expected_canonical:
        returned = {str(doc.get("section_id") or "").strip() for doc in valid}
        matched = len(expected_canonical.intersection(returned))
        if matched == 0:
            raise ValueError(
                "Retrieval smoke check returned no expected section IDs: "
                + ", ".join(sorted(expected_canonical))
            )

    sample = []
    for doc in valid[:5]:
        sample.append(
            {
                "section_id": str(doc.get("section_id") or ""),
                "score": doc.get("score"),
                "text_preview": str(doc.get("text") or "")[:160],
            }
        )
    return len(valid), matched, sample


def build_snapshot_index_bundle(
    *,
    corpus_path: Path,
    out_base: Path = Path("dist") / "index",
    model_name: str = "all-MiniLM-L12-v2",
    verify_pipeline_env: bool = True,
    smoke_query: str | None = None,
    smoke_top_k: int = 5,
    expected_sections: Sequence[str] | None = None,
) -> SnapshotIndexBundle:
    """Build a snapshot-scoped FAISS index and validate metadata + env wiring."""

    corpus_path = Path(corpus_path)
    docs = load_corpus_jsonl(corpus_path)
    require_valid_corpus(docs)
    docs = sorted(docs, key=lambda d: str(d.get("doc_id") or ""))
    snapshot_id = _resolve_snapshot_id(docs, corpus_path)

    index_dir = Path(out_base) / snapshot_id
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "index.faiss"
    meta_path = index_dir / "index.meta.json"

    build_faiss_index_from_corpus(
        docs,
        index_path=index_path,
        meta_path=meta_path,
        embedding_model=model_name,
    )

    corpus_digest = compute_corpus_digest(docs)
    meta = _read_meta(meta_path)
    build_timestamp_utc = _verify_meta_contract(
        meta,
        expected_model=model_name,
        expected_digest=corpus_digest,
        expected_doc_count=len(docs),
    )
    env_file, env_ps1 = _write_runtime_env_files(
        index_dir, index_path=index_path, model_name=model_name
    )

    env_check: dict[str, Any] | None = None
    smoke_samples: list[dict[str, Any]] = []
    smoke_result_count = 0
    smoke_expected_hits = 0
    retriever_obj: object | None = None
    if verify_pipeline_env or smoke_query:
        retriever_obj, retr_cfg = _verify_pipeline_env_wiring(
            index_path=index_path,
            model_name=model_name,
        )
        env_check = {
            "ok": True,
            "retriever": retr_cfg,
        }
    if smoke_query:
        if retriever_obj is None:
            raise ValueError("Internal error: retriever unavailable for smoke query")
        smoke_result_count, smoke_expected_hits, smoke_samples = _run_retrieval_smoke(
            retriever=retriever_obj,
            query=smoke_query,
            top_k=smoke_top_k,
            expected_sections=expected_sections,
        )

    build_log = {
        "schema_version": INDEX_BUILD_LOG_VERSION,
        "snapshot_id": snapshot_id,
        "corpus": {
            "path": str(corpus_path),
            "digest": corpus_digest,
            "doc_count": len(docs),
        },
        "index": {
            "path": str(index_path),
            "sha256": compute_sha256_hex(index_path),
        },
        "metadata": {
            "path": str(meta_path),
            "sha256": compute_sha256_hex(meta_path),
            "schema_version": str(meta.get("schema_version") or ""),
            "build_timestamp_utc": build_timestamp_utc,
            "embedding_model": str(meta.get("embedding_model") or ""),
            "corpus_digest": str(meta.get("corpus_digest") or ""),
            "doc_count": int(meta.get("doc_count") or 0),
        },
        "runtime_env": {
            "env_file": str(env_file),
            "powershell_file": str(env_ps1),
            "EARCRAWLER_FAISS_INDEX": str(index_path.resolve()),
            "EARCRAWLER_FAISS_MODEL": model_name,
        },
        "env_check": env_check or {"ok": False},
        "smoke": {
            "query": smoke_query,
            "top_k": smoke_top_k,
            "result_count": smoke_result_count,
            "expected_section_hits": smoke_expected_hits,
            "results": smoke_samples,
        },
    }
    build_log_path = index_dir / "index_build_log.json"
    build_log_path.write_text(
        json.dumps(build_log, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return SnapshotIndexBundle(
        snapshot_id=snapshot_id,
        index_dir=index_dir,
        index_path=index_path,
        meta_path=meta_path,
        build_log_path=build_log_path,
        env_file_path=env_file,
        env_ps1_path=env_ps1,
        embedding_model=model_name,
        corpus_digest=corpus_digest,
        doc_count=len(docs),
        build_timestamp_utc=build_timestamp_utc,
        smoke_result_count=smoke_result_count,
        smoke_expected_hits=smoke_expected_hits,
    )


__all__ = [
    "INDEX_BUILD_LOG_VERSION",
    "SnapshotIndexBundle",
    "build_snapshot_index_bundle",
]
