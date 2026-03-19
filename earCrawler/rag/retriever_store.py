from __future__ import annotations

"""Artifact loading/saving and cache helpers for Retriever."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, MutableMapping

from earCrawler.rag.index_builder import INDEX_META_VERSION
from earCrawler.rag.retriever_ranking import (
    build_bm25_state,
    document_text_for_embedding,
    materialize_metadata_rows,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RetrieverArtifactStore:
    """Encapsulates index + metadata IO and in-memory artifact caches."""

    def __init__(
        self,
        *,
        index_path: Path,
        model_name: str,
        allow_legacy_pickle_metadata: bool,
        logger,
        model,
        retry_fn: Callable,
        np_mod,
        faiss_mod,
        cache_lock,
        index_cache: MutableMapping[str, tuple[int, int, object]],
        meta_cache: MutableMapping[str, tuple[int, int, list[dict]]],
        embedding_cache: MutableMapping[str, tuple[int, int, object]],
        bm25_cache: MutableMapping[str, tuple[int, int, dict[str, object]]],
        retriever_error_cls,
        index_missing_error_cls,
        index_build_required_error_cls,
    ) -> None:
        self.index_path = Path(index_path)
        self.meta_path = self.index_path.with_suffix(".meta.json")
        self.legacy_meta_path = self.index_path.with_suffix(".pkl")
        self.model_name = model_name
        self.allow_legacy_pickle_metadata = allow_legacy_pickle_metadata
        self.logger = logger
        self.model = model
        self._retry = retry_fn
        self._np = np_mod
        self._faiss = faiss_mod
        self._cache_lock = cache_lock
        self._index_cache = index_cache
        self._meta_cache = meta_cache
        self._embedding_cache = embedding_cache
        self._bm25_cache = bm25_cache
        self._retriever_error_cls = retriever_error_cls
        self._index_missing_error_cls = index_missing_error_cls
        self._index_build_required_error_cls = index_build_required_error_cls

    def cache_token(self, path: Path) -> tuple[int, int]:
        stat = path.stat()
        return int(stat.st_mtime_ns), int(stat.st_size)

    def create_index(self, dim: int):
        if self._faiss is None:
            return None
        base = self._faiss.IndexFlatL2(dim)
        return self._faiss.IndexIDMap(base)

    def load_index(self, dim: int, *, allow_create: bool = False):
        if self._faiss is None:
            return None
        if self.index_path.exists():
            key = str(self.index_path)
            token = self.cache_token(self.index_path)
            with self._cache_lock:
                cached = self._index_cache.get(key)
            if cached is not None and cached[:2] == token:
                self.logger.info("rag.retriever.index_cache_hit index_path=%s", key)
                return cached[2]
            self.logger.info("rag.retriever.index_cache_miss index_path=%s", key)
            try:
                index = self._faiss.read_index(str(self.index_path))
            except Exception as exc:
                raise self._index_build_required_error_cls(
                    self.index_path, reason=f"unable to read index: {exc}"
                ) from exc
            IndexIDMap = getattr(self._faiss, "IndexIDMap", None)
            if isinstance(IndexIDMap, type) and not isinstance(index, IndexIDMap):
                index = IndexIDMap(index)
            with self._cache_lock:
                self._index_cache[key] = (token[0], token[1], index)
            return index
        if not allow_create:
            raise self._index_missing_error_cls(self.index_path)
        return self.create_index(dim)

    def load_metadata(self, *, allow_create: bool = False) -> list[dict]:
        if self.meta_path.exists():
            key = str(self.meta_path)
            token = self.cache_token(self.meta_path)
            with self._cache_lock:
                cached = self._meta_cache.get(key)
            if cached is not None and cached[:2] == token:
                return materialize_metadata_rows(list(cached[2]))
            try:
                meta_obj = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise self._index_build_required_error_cls(
                    self.index_path, reason=f"failed to read metadata: {exc}"
                ) from exc
            rows: list[dict]
            if isinstance(meta_obj, dict) and isinstance(meta_obj.get("rows"), list):
                rows = materialize_metadata_rows(list(meta_obj["rows"]))
                with self._cache_lock:
                    self._meta_cache[key] = (token[0], token[1], list(rows))
                return rows
            if isinstance(meta_obj, list):
                rows = materialize_metadata_rows(list(meta_obj))
                with self._cache_lock:
                    self._meta_cache[key] = (token[0], token[1], list(rows))
                return rows
            raise self._index_build_required_error_cls(
                self.index_path, reason="metadata rows missing or invalid"
            )
        if self.allow_legacy_pickle_metadata and self.legacy_meta_path.exists():
            key = str(self.legacy_meta_path)
            token = self.cache_token(self.legacy_meta_path)
            with self._cache_lock:
                cached = self._meta_cache.get(key)
            if cached is not None and cached[:2] == token:
                return materialize_metadata_rows(list(cached[2]))
            try:
                import pickle

                self.logger.warning(
                    "rag.retriever.legacy_pickle_metadata_enabled env_var=%s path=%s",
                    "EARCRAWLER_ENABLE_LEGACY_PICKLE_METADATA",
                    self.legacy_meta_path,
                )
                with self.legacy_meta_path.open("rb") as fh:
                    rows = pickle.load(fh)
            except Exception as exc:
                raise self._index_build_required_error_cls(
                    self.index_path, reason=f"failed to read metadata: {exc}"
                ) from exc
            rows = materialize_metadata_rows(list(rows))
            with self._cache_lock:
                self._meta_cache[key] = (token[0], token[1], list(rows))
            return list(rows)
        if allow_create:
            return []
        raise self._index_build_required_error_cls(
            self.index_path, reason="metadata file missing"
        )

    def save_index(
        self,
        index,
        metadata: list[dict],
        *,
        corpus_digest: str | None = None,
    ) -> None:
        metadata = materialize_metadata_rows(metadata)
        if self._faiss is not None and index is not None:
            self._faiss.write_index(index, str(self.index_path))

        meta_payload = {
            "schema_version": INDEX_META_VERSION,
            "build_timestamp_utc": _utc_now_iso(),
            "corpus_schema_version": None,
            "corpus_digest": corpus_digest,
            "doc_count": len(metadata),
            "embedding_model": self.model_name,
            "rows": metadata,
        }
        try:
            meta_payload["corpus_schema_version"] = metadata[0].get("schema_version")
        except Exception:
            meta_payload["corpus_schema_version"] = None

        self.meta_path.write_text(
            json.dumps(meta_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self._cache_lock:
            if self.index_path.exists() and index is not None:
                self._index_cache[str(self.index_path)] = (
                    *self.cache_token(self.index_path),
                    index,
                )
            else:
                self._index_cache.pop(str(self.index_path), None)
            self._meta_cache[str(self.meta_path)] = (
                *self.cache_token(self.meta_path),
                list(metadata),
            )
            self._embedding_cache.pop(
                f"{self.model_name}::{self.meta_path.resolve()}",
                None,
            )
            self._bm25_cache.pop(f"bm25::{self.meta_path.resolve()}", None)
            self._bm25_cache.pop(f"bm25::{self.legacy_meta_path.resolve()}", None)

    def load_embedding_matrix(self, metadata: list[dict]):
        if self.meta_path.exists():
            cache_path = self.meta_path
        elif self.allow_legacy_pickle_metadata and self.legacy_meta_path.exists():
            cache_path = self.legacy_meta_path
        else:
            raise self._index_build_required_error_cls(
                self.index_path, reason="metadata file missing"
            )
        key = f"{self.model_name}::{cache_path.resolve()}"
        token = self.cache_token(cache_path)
        with self._cache_lock:
            cached = self._embedding_cache.get(key)
        if cached is not None and cached[:2] == token:
            return cached[2]

        texts = [document_text_for_embedding(row) for row in metadata]
        matrix = self._retry(
            self.model.encode,
            texts,
            show_progress_bar=False,
        )
        matrix = self._np.asarray(matrix).astype("float32")
        if matrix.ndim != 2 or matrix.shape[0] != len(metadata):
            raise self._retriever_error_cls(
                "Embedding model returned unexpected corpus matrix shape",
                code="embedding_shape_invalid",
                metadata={"row_count": len(metadata)},
            )
        norms = self._np.linalg.norm(matrix, axis=1, keepdims=True)
        zero_mask = norms == 0
        if self._np.any(zero_mask):
            norms = norms.copy()
            norms[zero_mask] = 1.0
        matrix = matrix / norms
        with self._cache_lock:
            self._embedding_cache[key] = (token[0], token[1], matrix)
        return matrix

    def load_bm25_state(self, metadata: list[dict]) -> dict[str, object]:
        if self.meta_path.exists():
            cache_path = self.meta_path
        elif self.allow_legacy_pickle_metadata and self.legacy_meta_path.exists():
            cache_path = self.legacy_meta_path
        else:
            raise self._index_build_required_error_cls(
                self.index_path, reason="metadata file missing"
            )
        key = f"bm25::{cache_path.resolve()}"
        token = self.cache_token(cache_path)
        with self._cache_lock:
            cached = self._bm25_cache.get(key)
        if cached is not None and cached[:2] == token:
            return dict(cached[2])

        state = build_bm25_state(metadata)
        with self._cache_lock:
            self._bm25_cache[key] = (token[0], token[1], dict(state))
        return state


__all__ = ["RetrieverArtifactStore"]
