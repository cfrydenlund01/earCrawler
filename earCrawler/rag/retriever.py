"""Lightweight RAG retriever built on FAISS and SentenceTransformers."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from threading import RLock
from typing import List, Mapping, MutableMapping, Optional

from earCrawler.utils.import_guard import import_optional

from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.rag.build_corpus import compute_corpus_digest
from earCrawler.rag.retriever_backend import (
    RETRIEVAL_BACKEND_ENV as _RETRIEVAL_BACKEND_ENV,
    RETRIEVAL_MODE_ENV as _RETRIEVAL_MODE_ENV,
    SUPPORTED_RETRIEVAL_BACKENDS as _SUPPORTED_RETRIEVAL_BACKENDS,
    SUPPORTED_RETRIEVAL_MODES as _SUPPORTED_RETRIEVAL_MODES,
    is_windows_platform as _is_windows_platform,
    legacy_pickle_metadata_enabled as _legacy_pickle_metadata_enabled,
    resolve_backend_name as _resolve_backend_name_internal,
    resolve_retrieval_mode as _resolve_retrieval_mode_internal,
)
from earCrawler.rag.retriever_citation_policy import (
    apply_citation_boost as _apply_citation_boost,
    extract_ear_section_targets as _extract_ear_section_targets,
)
from earCrawler.rag.retriever_ranking import (
    HYBRID_RRF_K as _HYBRID_RRF_K,
    fuse_rankings as _fuse_rankings_internal,
    hybrid_candidate_count as _hybrid_candidate_count_internal,
    metadata_tie_break_key as _metadata_tie_break_key,
    public_result_doc as _public_result_doc,
    rank_bm25 as _rank_bm25,
    score_bucket as _score_bucket,
)
from earCrawler.rag.retriever_store import RetrieverArtifactStore

SentenceTransformer = None  # type: ignore[assignment]
faiss = None  # type: ignore[assignment]
_MODEL_CACHE: dict[str, object] = {}
_INDEX_CACHE: dict[str, tuple[int, int, object]] = {}
_META_CACHE: dict[str, tuple[int, int, list[dict]]] = {}
_EMBEDDING_CACHE: dict[str, tuple[int, int, object]] = {}
_BM25_CACHE: dict[str, tuple[int, int, dict[str, object]]] = {}
_CACHE_LOCK = RLock()


class RetrieverError(RuntimeError):
    """Base class for retriever failures surfaced to callers."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "retriever_error",
        metadata: Optional[Mapping[str, object]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata: MutableMapping[str, object] = dict(metadata or {})


class RetrieverUnavailableError(RetrieverError):
    """Raised when optional dependencies cannot be loaded."""

    def __init__(self, message: str, *, metadata: Optional[Mapping[str, object]] = None):
        super().__init__(message, code="retriever_unavailable", metadata=metadata)


class RetrieverMisconfiguredError(RetrieverError):
    """Raised when configuration env vars or model paths are invalid."""

    def __init__(self, message: str, *, metadata: Optional[Mapping[str, object]] = None):
        super().__init__(message, code="retriever_misconfigured", metadata=metadata)


class IndexMissingError(RetrieverError):
    """Raised when a configured FAISS index path does not exist."""

    def __init__(self, path: Path, *, metadata: Optional[Mapping[str, object]] = None):
        hint = (
            "Build the index with: "
            f"`python -m earCrawler.cli rag_index build --input <corpus.jsonl> --index-path \"{path}\"` "
            "(writes index.faiss + index_meta.json)"
        )
        message = f"FAISS index missing at {path}. {hint}"
        md = {"index_path": str(path)}
        if metadata:
            md.update(metadata)
        super().__init__(message, code="index_missing", metadata=md)


class IndexBuildRequiredError(RetrieverError):
    """Raised when index metadata is missing or unreadable (index not built)."""

    def __init__(self, path: Path, *, reason: str | None = None):
        hint = (
            "Build the index with: "
            f"`python -m earCrawler.cli rag_index build --input <corpus.jsonl> --index-path \"{path}\"` "
            "(ensures index_meta.json is present)"
        )
        message = f"FAISS index at {path} is not ready."
        if reason:
            message = f"{message} ({reason})"
        super().__init__(
            f"{message} {hint}",
            code="index_build_required",
            metadata={"index_path": str(path), "reason": reason or "not_built"},
        )


def _resolve_backend_name(explicit_backend: str | None = None) -> tuple[str, str]:
    resolved, source = _resolve_backend_name_internal(explicit_backend)
    if resolved is not None:
        return resolved, source

    raw = explicit_backend
    if raw is None:
        raw = os.getenv(_RETRIEVAL_BACKEND_ENV)
    raise RetrieverMisconfiguredError(
        f"Unsupported retrieval backend '{raw}'",
        metadata={
            "backend": raw,
            "supported_backends": sorted(_SUPPORTED_RETRIEVAL_BACKENDS),
            "env_var": _RETRIEVAL_BACKEND_ENV,
        },
    )


def _resolve_retrieval_mode(explicit_mode: str | None = None) -> tuple[str, str]:
    resolved, source = _resolve_retrieval_mode_internal(explicit_mode)
    if resolved is not None:
        return resolved, source

    raw = explicit_mode
    if raw is None:
        raw = os.getenv(_RETRIEVAL_MODE_ENV)
    raise RetrieverMisconfiguredError(
        f"Unsupported retrieval mode '{raw}'",
        metadata={
            "retrieval_mode": raw,
            "supported_modes": sorted(_SUPPORTED_RETRIEVAL_MODES),
            "env_var": _RETRIEVAL_MODE_ENV,
        },
    )


class Retriever:
    """Vector search over EAR documents using FAISS."""

    def __init__(
        self,
        tradegov_client: TradeGovClient,
        fedreg_client: FederalRegisterClient,
        model_name: str = "all-MiniLM-L12-v2",
        index_path: Path = Path("data/faiss/index.faiss"),
        backend: str | None = None,
        retrieval_mode: str | None = None,
    ) -> None:
        self.tradegov_client = tradegov_client
        self.fedreg_client = fedreg_client
        self.model_name = model_name
        resolved_backend, backend_source = _resolve_backend_name(backend)
        resolved_mode, mode_source = _resolve_retrieval_mode(retrieval_mode)
        self.backend = resolved_backend
        self.backend_source = backend_source
        self.retrieval_mode = resolved_mode
        self.retrieval_mode_source = mode_source
        self.hybrid_rrf_k = _HYBRID_RRF_K
        self.faiss_threads = None

        global SentenceTransformer
        if SentenceTransformer is None:
            try:
                sentence_transformers = import_optional(
                    "sentence_transformers", ["sentence-transformers"]
                )
            except RuntimeError as exc:
                raise RetrieverUnavailableError(
                    str(exc), metadata={"packages": ["sentence-transformers"]}
                ) from exc
            SentenceTransformer = sentence_transformers.SentenceTransformer

        self.index_path = Path(index_path)
        self.meta_path = self.index_path.with_suffix(".meta.json")
        self.legacy_meta_path = self.index_path.with_suffix(".pkl")
        self.allow_legacy_pickle_metadata = _legacy_pickle_metadata_enabled()
        self.logger = logging.getLogger(__name__)
        try:
            self.model = self._load_model(model_name)
        except Exception as exc:
            raise RetrieverMisconfiguredError(
                f"Failed to load SentenceTransformer model '{model_name}'",
                metadata={"model_name": model_name},
            ) from exc

        self._faiss = None
        if self.backend == "faiss":
            global faiss
            if faiss is None:
                try:
                    faiss = import_optional("faiss", ["faiss-cpu"])
                except RuntimeError as exc:
                    raise RetrieverUnavailableError(
                        str(exc),
                        metadata={"packages": ["faiss-cpu"], "backend": self.backend},
                    ) from exc
            self._faiss = faiss
            self._configure_faiss_determinism()
        try:
            self._np = import_optional("numpy", ["numpy"])
        except RuntimeError as exc:
            raise RetrieverUnavailableError(
                str(exc), metadata={"packages": ["numpy"]}
            ) from exc

        self._artifact_store = RetrieverArtifactStore(
            index_path=self.index_path,
            model_name=self.model_name,
            allow_legacy_pickle_metadata=self.allow_legacy_pickle_metadata,
            logger=self.logger,
            model=self.model,
            retry_fn=self._retry,
            np_mod=self._np,
            faiss_mod=self._faiss,
            cache_lock=_CACHE_LOCK,
            index_cache=_INDEX_CACHE,
            meta_cache=_META_CACHE,
            embedding_cache=_EMBEDDING_CACHE,
            bm25_cache=_BM25_CACHE,
            retriever_error_cls=RetrieverError,
            index_missing_error_cls=IndexMissingError,
            index_build_required_error_cls=IndexBuildRequiredError,
        )

        # Status flags for external introspection/logging.
        self.enabled = True
        self.ready = True
        self.failure_type: str | None = None

    def _configure_faiss_determinism(self) -> None:
        if self._faiss is None:
            return
        omp_set_num_threads = getattr(self._faiss, "omp_set_num_threads", None)
        if callable(omp_set_num_threads):
            omp_set_num_threads(1)
            self.faiss_threads = 1

    def _load_model(self, model_name: str):
        with _CACHE_LOCK:
            cached = _MODEL_CACHE.get(model_name)
        if cached is not None:
            self.logger.info("rag.retriever.model_cache_hit model_name=%s", model_name)
            return cached

        self.logger.info("rag.retriever.model_cache_miss model_name=%s", model_name)
        model_obj = SentenceTransformer(model_name)  # type: ignore[misc]
        with _CACHE_LOCK:
            _MODEL_CACHE[model_name] = model_obj
        return model_obj

    def _cache_token(self, path: Path) -> tuple[int, int]:
        return self._artifact_store.cache_token(path)

    def _retry(self, func, *args, **kwargs):
        attempts = 3
        delay = 1.0
        for attempt in range(attempts):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - unexpected
                if attempt < attempts - 1:
                    self.logger.warning("Operation failed: %s; retrying", exc)
                    time.sleep(delay)
                    delay *= 2
                    continue
                self.logger.error("Operation failed after retries: %s", exc)
                raise

    def _create_index(self, dim: int):
        return self._artifact_store.create_index(dim)

    def _load_index(self, dim: int, *, allow_create: bool = False):
        return self._artifact_store.load_index(dim, allow_create=allow_create)

    def _load_metadata(self, *, allow_create: bool = False) -> List[dict]:
        return self._artifact_store.load_metadata(allow_create=allow_create)

    def _save_index(
        self,
        index,
        metadata: List[dict],
        corpus_digest: str | None = None,
    ) -> None:
        self._artifact_store.save_index(
            index=index,
            metadata=metadata,
            corpus_digest=corpus_digest,
        )

    def add_documents(self, docs: List[dict]) -> None:
        """Add ``docs`` to the retrieval index."""
        if not docs:
            self.logger.info("No documents provided for indexing")
            return

        try:
            from earCrawler.rag.corpus_contract import require_valid_corpus
        except Exception as exc:  # pragma: no cover - import failure
            raise RetrieverError(str(exc), code="corpus_validation_failed") from exc

        existing = self._load_metadata(allow_create=True)
        combined = list(existing) + list(docs)
        require_valid_corpus(combined)
        combined = sorted(combined, key=lambda d: str(d.get("doc_id") or ""))
        texts = [
            str(
                d.get("text")
                or d.get("body")
                or d.get("summary")
                or d.get("title")
                or ""
            )
            for d in combined
        ]

        vectors = self._retry(
            self.model.encode,
            texts,
            show_progress_bar=False,
        )
        vectors = self._np.asarray(vectors).astype("float32")
        dim = vectors.shape[1]

        index = self._create_index(dim) if self.backend == "faiss" else None
        if index is not None:
            ids = self._np.arange(0, len(vectors))
            index.add_with_ids(vectors, ids)

        digest = None
        try:
            digest = compute_corpus_digest(combined)
        except Exception:
            digest = None

        self._save_index(index, combined, corpus_digest=digest)
        self.logger.info("Indexed %d documents", len(combined))

    def _load_embedding_matrix(self, metadata: List[dict]):
        return self._artifact_store.load_embedding_matrix(metadata)

    def _load_bm25_state(self, metadata: List[dict]) -> dict[str, object]:
        return self._artifact_store.load_bm25_state(metadata)

    def _hybrid_candidate_count(self, *, k: int, total_docs: int) -> int:
        return _hybrid_candidate_count_internal(k=k, total_docs=total_docs)

    def _query_dense(self, vector, metadata: List[dict], *, k: int) -> List[dict]:
        if self.backend == "faiss":
            return self._query_faiss(vector, metadata, k=k)
        return self._query_bruteforce(vector, metadata, k=k)

    def _query_bruteforce(self, vector, metadata: List[dict], *, k: int) -> List[dict]:
        matrix = self._load_embedding_matrix(metadata)
        query = self._np.asarray(vector).astype("float32")
        if query.ndim != 2 or query.shape[0] != 1:
            raise RetrieverError(
                "Embedding model returned unexpected query vector shape",
                code="embedding_shape_invalid",
            )
        query_norms = self._np.linalg.norm(query, axis=1, keepdims=True)
        zero_mask = query_norms == 0
        if self._np.any(zero_mask):
            query_norms = query_norms.copy()
            query_norms[zero_mask] = 1.0
        query = query / query_norms
        scores = self._np.matmul(matrix, query[0]).astype("float32")

        ranked: list[tuple[int, int, tuple[str, str, int]]] = []
        for idx, score in enumerate(scores.tolist()):
            ranked.append(
                (
                    idx,
                    _score_bucket(score),
                    _metadata_tie_break_key(metadata[idx], idx),
                )
            )

        ranked.sort(key=lambda item: (-item[1], item[2]))

        results: list[dict] = []
        for idx, _bucket, _tie_key in ranked[: max(1, int(k))]:
            doc = _public_result_doc(metadata[idx])
            doc["score"] = float(scores[idx])
            results.append(doc)
        return results

    def _query_bm25(self, prompt: str, metadata: List[dict], *, k: int) -> List[dict]:
        state = self._load_bm25_state(metadata)
        return _rank_bm25(prompt, metadata, state=state, k=k)

    def _query_faiss(self, vector, metadata: List[dict], *, k: int) -> List[dict]:
        index = self._load_index(vector.shape[1])
        index_size_raw = getattr(index, "ntotal", None)
        try:
            index_size = int(index_size_raw) if index_size_raw is not None else None
        except Exception:
            index_size = None
        if index_size is not None and index_size > 0 and index_size != len(metadata):
            raise IndexBuildRequiredError(
                self.index_path, reason="index/meta size mismatch"
            )

        search_k = len(metadata) if _is_windows_platform() else max(1, int(k))
        distances, indices = index.search(vector, search_k)

        ranked: list[tuple[int, int, tuple[str, str, int], float]] = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(metadata):
                continue
            score = float(1.0 / (1.0 + float(distance)))
            ranked.append(
                (
                    int(idx),
                    _score_bucket(score),
                    _metadata_tie_break_key(metadata[int(idx)], int(idx)),
                    score,
                )
            )

        ranked.sort(key=lambda item: (-item[1], item[2]))

        results: list[dict] = []
        for idx, _bucket, _tie_key, score in ranked[: max(1, int(k))]:
            doc = _public_result_doc(metadata[idx])
            doc["score"] = score
            results.append(doc)
        return results

    def _fuse_rankings(
        self,
        *,
        metadata: List[dict],
        dense_results: List[dict],
        bm25_results: List[dict],
        k: int,
    ) -> List[dict]:
        return _fuse_rankings_internal(
            metadata=metadata,
            dense_results=dense_results,
            bm25_results=bm25_results,
            k=k,
            rrf_k=self.hybrid_rrf_k,
        )

    def query(self, prompt: str, k: int = 5) -> List[dict]:
        """Return top ``k`` documents matching ``prompt``."""
        if self.backend == "faiss" and not self.index_path.exists():
            raise IndexMissingError(self.index_path)
        if not self.meta_path.exists() and not (
            self.allow_legacy_pickle_metadata and self.legacy_meta_path.exists()
        ):
            raise IndexBuildRequiredError(
                self.index_path, reason="metadata file missing"
            )

        embedding = self._retry(
            self.model.encode,
            [prompt],
            show_progress_bar=False,
        )
        vector = self._np.asarray(embedding).astype("float32")
        metadata = self._load_metadata()
        if self.retrieval_mode == "hybrid":
            candidate_k = self._hybrid_candidate_count(k=k, total_docs=len(metadata))
            dense_results = self._query_dense(vector, metadata, k=candidate_k)
            bm25_results = self._query_bm25(prompt, metadata, k=candidate_k)
            results = self._fuse_rankings(
                metadata=metadata,
                dense_results=dense_results,
                bm25_results=bm25_results,
                k=k,
            )
        else:
            results = self._query_dense(vector, metadata, k=k)

        return _apply_citation_boost(prompt, results=results, metadata=metadata, k=k)

    def warm(self) -> None:
        """Pre-load embeddings and index metadata for faster first query."""
        embedding = self._retry(
            self.model.encode,
            ["earcrawler warmup"],
            show_progress_bar=False,
        )
        vector = self._np.asarray(embedding).astype("float32")
        dim = vector.shape[1]
        if self.backend == "faiss" and self.index_path.exists():
            self._load_index(dim)
        metadata: list[dict] = []
        if self.meta_path.exists() or (
            self.allow_legacy_pickle_metadata and self.legacy_meta_path.exists()
        ):
            metadata = self._load_metadata(allow_create=True)
        if self.backend == "bruteforce" and metadata:
            self._load_embedding_matrix(metadata)
        if self.retrieval_mode == "hybrid" and metadata:
            self._load_bm25_state(metadata)


def describe_retriever_config(obj: object) -> dict[str, object]:
    """Return a best-effort snapshot of retriever configuration for logging."""

    index_path = getattr(obj, "index_path", None)
    if isinstance(index_path, Path):
        index_path = str(index_path)
    return {
        "index_path": index_path,
        "model_name": getattr(obj, "model_name", None),
        "mode": getattr(obj, "retrieval_mode", None),
        "mode_source": getattr(obj, "retrieval_mode_source", None),
        "backend": getattr(obj, "backend", None),
        "backend_source": getattr(obj, "backend_source", None),
        "hybrid_rrf_k": getattr(obj, "hybrid_rrf_k", None),
        "faiss_threads": getattr(obj, "faiss_threads", None),
        "enabled": bool(getattr(obj, "enabled", True)),
        "ready": bool(getattr(obj, "ready", True)),
        "failure_type": getattr(obj, "failure_type", None),
    }


__all__ = [
    "IndexBuildRequiredError",
    "IndexMissingError",
    "Retriever",
    "RetrieverError",
    "RetrieverMisconfiguredError",
    "RetrieverUnavailableError",
    "_apply_citation_boost",
    "_extract_ear_section_targets",
    "_resolve_backend_name",
    "_resolve_retrieval_mode",
    "describe_retriever_config",
]
