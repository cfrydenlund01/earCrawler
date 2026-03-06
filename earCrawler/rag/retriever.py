"""Lightweight RAG retriever built on FAISS and SentenceTransformers."""

from __future__ import annotations

import logging
import json
import os
import time
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import List, Mapping, MutableMapping, Optional

from earCrawler.utils.import_guard import import_optional

SentenceTransformer = None  # type: ignore[assignment]
faiss = None  # type: ignore[assignment]
_MODEL_CACHE: dict[str, object] = {}
_INDEX_CACHE: dict[str, tuple[int, int, object]] = {}
_META_CACHE: dict[str, tuple[int, int, list[dict]]] = {}
_EMBEDDING_CACHE: dict[str, tuple[int, int, object]] = {}
_CACHE_LOCK = RLock()

from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.rag.build_corpus import compute_corpus_digest
from earCrawler.rag.index_builder import INDEX_META_VERSION


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_CFR_CITATION_RE = re.compile(
    r"(?:§\s*)?(?P<section>\d{3}\.\d+(?:\([A-Za-z0-9]+\))*)",
    flags=re.IGNORECASE,
)
_RETRIEVAL_BACKEND_ENV = "EARCRAWLER_RETRIEVAL_BACKEND"
_LEGACY_PICKLE_METADATA_ENV = "EARCRAWLER_ENABLE_LEGACY_PICKLE_METADATA"
_SUPPORTED_RETRIEVAL_BACKENDS = {"faiss", "bruteforce"}
_SCORE_TIE_EPSILON = 1e-6


def _extract_ear_section_targets(prompt: str) -> list[str]:
    """Extract EAR-style section ids from explicit CFR citations in ``prompt``.

    Intended for deterministic boosting when the user query includes an explicit
    section citation like "15 CFR 740.1" or "§ 736.2(b)(4)".
    """

    raw = str(prompt or "")
    seen: set[str] = set()
    targets: list[str] = []
    for match in _CFR_CITATION_RE.finditer(raw):
        sec = str(match.group("section") or "").strip()
        if not sec:
            continue
        exact = f"EAR-{sec}"
        if exact not in seen:
            targets.append(exact)
            seen.add(exact)
        if "(" in sec:
            base = f"EAR-{sec.split('(', 1)[0]}"
            if base not in seen:
                targets.append(base)
                seen.add(base)
    return targets


def _is_windows_platform() -> bool:
    return sys.platform.startswith("win")


def _default_backend_name() -> str:
    return "bruteforce" if _is_windows_platform() else "faiss"


def _legacy_pickle_metadata_enabled() -> bool:
    raw = os.getenv(_LEGACY_PICKLE_METADATA_ENV)
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_backend_name(explicit_backend: str | None = None) -> tuple[str, str]:
    raw = explicit_backend
    source = "default"
    if raw is None:
        raw = os.getenv(_RETRIEVAL_BACKEND_ENV)
        if raw is not None:
            source = f"env:{_RETRIEVAL_BACKEND_ENV}"
    else:
        source = "argument"

    if raw is None:
        return _default_backend_name(), source

    backend = str(raw).strip().lower()
    if backend not in _SUPPORTED_RETRIEVAL_BACKENDS:
        raise RetrieverMisconfiguredError(
            f"Unsupported retrieval backend '{raw}'",
            metadata={
                "backend": raw,
                "supported_backends": sorted(_SUPPORTED_RETRIEVAL_BACKENDS),
                "env_var": _RETRIEVAL_BACKEND_ENV,
            },
        )
    return backend, source


def _canonical_section_id(row: Mapping[str, object]) -> str | None:
    raw = row.get("section_id") or row.get("section") or row.get("doc_id") or row.get("id")
    if raw is None:
        return None
    sec = str(raw).strip()
    if not sec:
        return None
    if sec.upper().startswith("EAR-"):
        if "#" in sec:
            sec = sec.split("#", 1)[0].strip()
        return sec
    return None


def _metadata_row_order(row: Mapping[str, object], fallback_order: int) -> int:
    raw = row.get("row_id")
    try:
        return int(raw) if raw is not None else fallback_order
    except Exception:
        return fallback_order


def _metadata_tie_break_key(row: Mapping[str, object], fallback_order: int) -> tuple[str, str, int]:
    section_id = _canonical_section_id(row) or ""
    chunk_or_doc_id = str(row.get("chunk_id") or row.get("doc_id") or row.get("id") or "")
    return (section_id, chunk_or_doc_id, _metadata_row_order(row, fallback_order))


def _score_bucket(score: object) -> int:
    try:
        return int(round(float(score) / _SCORE_TIE_EPSILON))
    except Exception:
        return 0


def _document_text_for_embedding(row: Mapping[str, object]) -> str:
    for key in ("text", "body", "content", "paragraph", "summary", "snippet", "title"):
        value = row.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _materialize_metadata_rows(metadata: List[dict]) -> List[dict]:
    rows: list[dict] = []
    for idx, row in enumerate(metadata):
        materialized = dict(row)
        materialized.setdefault("row_id", idx)
        rows.append(materialized)
    return rows


def _public_result_doc(row: Mapping[str, object]) -> dict:
    doc = dict(row)
    doc.pop("row_id", None)
    if "section_id" not in doc and doc.get("doc_id"):
        doc["section_id"] = str(doc.get("doc_id")).split("#", 1)[0]
    return doc


def _best_metadata_row_for_section(metadata: list[dict], target_section_id: str) -> dict | None:
    """Select the best row to represent ``target_section_id`` from metadata."""

    best: dict | None = None
    best_score = -1_000_000
    target = str(target_section_id or "").strip()
    if not target:
        return None

    for row in metadata:
        sec = _canonical_section_id(row)
        if sec != target:
            continue
        doc_id = str(row.get("doc_id") or "")
        chunk_kind = str(row.get("chunk_kind") or "")
        ordinal_raw = row.get("ordinal")
        try:
            ordinal = int(ordinal_raw) if ordinal_raw is not None else None
        except Exception:
            ordinal = None

        score = 0
        if doc_id == target:
            score += 100
        elif doc_id.startswith(target + "#"):
            score += 60
        if chunk_kind == "section":
            score += 10
        if ordinal == 0:
            score += 5
        if score > best_score:
            best = row
            best_score = score

    if best is None:
        return None
    chosen = dict(best)
    chosen.setdefault("section_id", target)
    return chosen


def _apply_citation_boost(
    prompt: str,
    *,
    results: list[dict],
    metadata: list[dict],
    k: int,
) -> list[dict]:
    """Ensure explicitly cited sections appear in the top-K results."""

    targets = _extract_ear_section_targets(prompt)
    if not targets:
        return results

    # Build a stable set of section ids present in the current result list.
    present_sections: set[str] = set()
    for row in results:
        sec = _canonical_section_id(row) or _canonical_section_id({"doc_id": row.get("doc_id")})
        if sec:
            present_sections.add(sec)

    boosted: list[dict] = []
    for target in targets:
        if target in present_sections:
            continue
        row = _best_metadata_row_for_section(metadata, target)
        if row is None:
            continue
        boosted.append(row)
        present_sections.add(target)

    if not boosted:
        return results

    # Assign deterministic scores above existing results (score is not used for matching,
    # but callers may log it).
    max_score = 0.0
    for row in results:
        try:
            val = float(row.get("score") or 0.0)
        except Exception:
            val = 0.0
        if val > max_score:
            max_score = val

    bump = max_score + 1.0
    for idx, row in enumerate(boosted):
        out = dict(row)
        out.pop("row_id", None)
        out.setdefault("boost_reason", "explicit_citation")
        out["score"] = bump - (idx * 0.001)
        boosted[idx] = out

    # Prepend boosted rows and truncate to top-K.
    return (boosted + list(results))[: max(1, int(k))]


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


class Retriever:
    """Vector search over EAR documents using FAISS.

    Parameters
    ----------
    tradegov_client:
        Instance of :class:`TradeGovClient` used for future expansions.
    fedreg_client:
        Instance of :class:`FederalRegisterClient` used for future expansions.
    model_name:
        SentenceTransformer model name.
    index_path:
        Location of the FAISS index file.

    Notes
    -----
    Load API keys from Windows Credential Store—never hard-code.
    Secure your FAISS index path and model files.
    """

    def __init__(
        self,
        tradegov_client: TradeGovClient,
        fedreg_client: FederalRegisterClient,
        model_name: str = "all-MiniLM-L12-v2",
        index_path: Path = Path("data/faiss/index.faiss"),
        backend: str | None = None,
    ) -> None:
        self.tradegov_client = tradegov_client
        self.fedreg_client = fedreg_client
        self.model_name = model_name
        resolved_backend, backend_source = _resolve_backend_name(backend)
        self.backend = resolved_backend
        self.backend_source = backend_source
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
                        str(exc), metadata={"packages": ["faiss-cpu"], "backend": self.backend}
                    ) from exc
            self._faiss = faiss
            self._configure_faiss_determinism()
        try:
            self._np = import_optional("numpy", ["numpy"])
        except RuntimeError as exc:
            raise RetrieverUnavailableError(
                str(exc), metadata={"packages": ["numpy"]}
            ) from exc
        # Status flags for external introspection/logging.
        self.enabled = True
        self.ready = True
        self.failure_type: str | None = None

    # ------------------------------------------------------------------
    def _configure_faiss_determinism(self) -> None:
        faiss_mod = self._faiss
        if faiss_mod is None:
            return
        omp_set_num_threads = getattr(faiss_mod, "omp_set_num_threads", None)
        if callable(omp_set_num_threads):
            omp_set_num_threads(1)
            self.faiss_threads = 1

    # ------------------------------------------------------------------
    def _load_model(self, model_name: str):
        with _CACHE_LOCK:
            cached = _MODEL_CACHE.get(model_name)
        if cached is not None:
            self.logger.info(
                "rag.retriever.model_cache_hit model_name=%s", model_name
            )
            return cached

        self.logger.info("rag.retriever.model_cache_miss model_name=%s", model_name)
        model_obj = SentenceTransformer(model_name)  # type: ignore[misc]
        with _CACHE_LOCK:
            _MODEL_CACHE[model_name] = model_obj
        return model_obj

    # ------------------------------------------------------------------
    def _cache_token(self, path: Path) -> tuple[int, int]:
        stat = path.stat()
        return int(stat.st_mtime_ns), int(stat.st_size)

    # ------------------------------------------------------------------
    def _retry(self, func, *args, **kwargs):
        """Execute ``func`` with retries and exponential backoff.

        Parameters
        ----------
        func:
            Callable to run.
        *args:
            Positional arguments forwarded to ``func``.
        **kwargs:
            Keyword arguments forwarded to ``func``.

        Returns
        -------
        Any
            The return value of ``func`` if it succeeds.

        Notes
        -----
        The callable is attempted up to three times with delays of
        1, 2 and 4 seconds between tries.
        """
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

    # ------------------------------------------------------------------
    def _create_index(self, dim: int):
        faiss_mod = self._faiss
        base = faiss_mod.IndexFlatL2(dim)
        return faiss_mod.IndexIDMap(base)

    def _load_index(self, dim: int, *, allow_create: bool = False):
        faiss_mod = self._faiss
        if self.index_path.exists():
            key = str(self.index_path)
            token = self._cache_token(self.index_path)
            with _CACHE_LOCK:
                cached = _INDEX_CACHE.get(key)
            if cached is not None and cached[:2] == token:
                self.logger.info("rag.retriever.index_cache_hit index_path=%s", key)
                return cached[2]
            self.logger.info("rag.retriever.index_cache_miss index_path=%s", key)
            try:
                index = faiss_mod.read_index(str(self.index_path))
            except Exception as exc:
                raise IndexBuildRequiredError(
                    self.index_path, reason=f"unable to read index: {exc}"
                ) from exc
            IndexIDMap = getattr(faiss_mod, "IndexIDMap", None)
            if isinstance(IndexIDMap, type) and not isinstance(index, IndexIDMap):  # pragma: no cover
                index = IndexIDMap(index)
            with _CACHE_LOCK:
                _INDEX_CACHE[key] = (token[0], token[1], index)
            return index
        if not allow_create:
            raise IndexMissingError(self.index_path)
        return self._create_index(dim)

    # ------------------------------------------------------------------
    def _load_metadata(self, *, allow_create: bool = False) -> List[dict]:
        if self.meta_path.exists():
            key = str(self.meta_path)
            token = self._cache_token(self.meta_path)
            with _CACHE_LOCK:
                cached = _META_CACHE.get(key)
            if cached is not None and cached[:2] == token:
                return _materialize_metadata_rows(list(cached[2]))
            try:
                meta_obj = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise IndexBuildRequiredError(
                    self.index_path, reason=f"failed to read metadata: {exc}"
                ) from exc
            rows: list[dict]
            if isinstance(meta_obj, dict) and isinstance(meta_obj.get("rows"), list):
                rows = _materialize_metadata_rows(list(meta_obj["rows"]))
                with _CACHE_LOCK:
                    _META_CACHE[key] = (token[0], token[1], list(rows))
                return rows
            if isinstance(meta_obj, list):
                rows = _materialize_metadata_rows(list(meta_obj))
                with _CACHE_LOCK:
                    _META_CACHE[key] = (token[0], token[1], list(rows))
                return rows
            raise IndexBuildRequiredError(
                self.index_path, reason="metadata rows missing or invalid"
            )
        if self.allow_legacy_pickle_metadata and self.legacy_meta_path.exists():
            key = str(self.legacy_meta_path)
            token = self._cache_token(self.legacy_meta_path)
            with _CACHE_LOCK:
                cached = _META_CACHE.get(key)
            if cached is not None and cached[:2] == token:
                return _materialize_metadata_rows(list(cached[2]))
            try:
                import pickle

                self.logger.warning(
                    "rag.retriever.legacy_pickle_metadata_enabled env_var=%s path=%s",
                    _LEGACY_PICKLE_METADATA_ENV,
                    self.legacy_meta_path,
                )
                with self.legacy_meta_path.open("rb") as fh:
                    rows = pickle.load(fh)
            except Exception as exc:
                raise IndexBuildRequiredError(
                    self.index_path, reason=f"failed to read metadata: {exc}"
                ) from exc
            rows = _materialize_metadata_rows(list(rows))
            with _CACHE_LOCK:
                _META_CACHE[key] = (token[0], token[1], list(rows))
            return list(rows)
        if allow_create:
            return []
        raise IndexBuildRequiredError(
            self.index_path, reason="metadata file missing"
        )

    # ------------------------------------------------------------------
    def _save_index(
        self,
        index,
        metadata: List[dict],
        corpus_digest: str | None = None,
    ) -> None:
        metadata = _materialize_metadata_rows(metadata)
        faiss_mod = self._faiss
        if faiss_mod is not None and index is not None:
            faiss_mod.write_index(index, str(self.index_path))

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
        with _CACHE_LOCK:
            if self.index_path.exists() and index is not None:
                _INDEX_CACHE[str(self.index_path)] = (
                    *self._cache_token(self.index_path),
                    index,
                )
            else:
                _INDEX_CACHE.pop(str(self.index_path), None)
            _META_CACHE[str(self.meta_path)] = (
                *self._cache_token(self.meta_path),
                list(metadata),
            )
            _EMBEDDING_CACHE.pop(
                f"{self.model_name}::{self.meta_path.resolve()}",
                None,
            )

    # ------------------------------------------------------------------
    def add_documents(self, docs: List[dict]) -> None:
        """Add ``docs`` to the FAISS index.

        Parameters
        ----------
        docs:
            List of contract-compliant corpus documents. Text is taken from ``text``,
            ``body``, ``summary`` or ``title`` fields.
        """
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

        texts = [str(d.get("text") or d.get("body") or d.get("summary") or d.get("title") or "") for d in combined]

        np_mod = self._np
        vectors = self._retry(
            self.model.encode,
            texts,
            show_progress_bar=False,
        )
        vectors = np_mod.asarray(vectors).astype("float32")
        dim = vectors.shape[1]

        index = self._create_index(dim) if self.backend == "faiss" else None
        ids = np_mod.arange(0, len(vectors))
        if index is not None:
            index.add_with_ids(vectors, ids)

        digest = None
        try:
            digest = compute_corpus_digest(combined)
        except Exception:
            digest = None

        self._save_index(index, combined, corpus_digest=digest)
        self.logger.info("Indexed %d documents", len(combined))

    # ------------------------------------------------------------------
    def _load_embedding_matrix(self, metadata: List[dict]):
        if self.meta_path.exists():
            cache_path = self.meta_path
        elif self.allow_legacy_pickle_metadata and self.legacy_meta_path.exists():
            cache_path = self.legacy_meta_path
        else:
            raise IndexBuildRequiredError(
                self.index_path, reason="metadata file missing"
            )
        key = f"{self.model_name}::{cache_path.resolve()}"
        token = self._cache_token(cache_path)
        with _CACHE_LOCK:
            cached = _EMBEDDING_CACHE.get(key)
        if cached is not None and cached[:2] == token:
            return cached[2]

        texts = [_document_text_for_embedding(row) for row in metadata]
        matrix = self._retry(
            self.model.encode,
            texts,
            show_progress_bar=False,
        )
        np_mod = self._np
        matrix = np_mod.asarray(matrix).astype("float32")
        if matrix.ndim != 2 or matrix.shape[0] != len(metadata):
            raise RetrieverError(
                "Embedding model returned unexpected corpus matrix shape",
                code="embedding_shape_invalid",
                metadata={"row_count": len(metadata)},
            )
        norms = np_mod.linalg.norm(matrix, axis=1, keepdims=True)
        zero_mask = norms == 0
        if np_mod.any(zero_mask):
            norms = norms.copy()
            norms[zero_mask] = 1.0
        matrix = matrix / norms
        with _CACHE_LOCK:
            _EMBEDDING_CACHE[key] = (token[0], token[1], matrix)
        return matrix

    # ------------------------------------------------------------------
    def _query_bruteforce(self, vector, metadata: List[dict], *, k: int) -> List[dict]:
        np_mod = self._np
        matrix = self._load_embedding_matrix(metadata)
        query = np_mod.asarray(vector).astype("float32")
        if query.ndim != 2 or query.shape[0] != 1:
            raise RetrieverError(
                "Embedding model returned unexpected query vector shape",
                code="embedding_shape_invalid",
            )
        query_norms = np_mod.linalg.norm(query, axis=1, keepdims=True)
        zero_mask = query_norms == 0
        if np_mod.any(zero_mask):
            query_norms = query_norms.copy()
            query_norms[zero_mask] = 1.0
        query = query / query_norms
        scores = np_mod.matmul(matrix, query[0]).astype("float32")

        ranked: list[tuple[int, int, tuple[str, str, int]]] = []
        for idx, score in enumerate(scores.tolist()):
            ranked.append((idx, _score_bucket(score), _metadata_tie_break_key(metadata[idx], idx)))

        ranked.sort(key=lambda item: (-item[1], item[2]))

        results: list[dict] = []
        for idx, _bucket, _tie_key in ranked[: max(1, int(k))]:
            doc = _public_result_doc(metadata[idx])
            doc["score"] = float(scores[idx])
            results.append(doc)
        return results

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
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
        np_mod = self._np
        embedding = self._retry(
            self.model.encode,
            [prompt],
            show_progress_bar=False,
        )
        vector = np_mod.asarray(embedding).astype("float32")
        metadata = self._load_metadata()
        if self.backend == "faiss":
            results = self._query_faiss(vector, metadata, k=k)
        else:
            results = self._query_bruteforce(vector, metadata, k=k)

        return _apply_citation_boost(prompt, results=results, metadata=metadata, k=k)

    # ------------------------------------------------------------------
    def warm(self) -> None:
        """Pre-load embeddings and index metadata for faster first query."""

        np_mod = self._np
        embedding = self._retry(
            self.model.encode,
            ["earcrawler warmup"],
            show_progress_bar=False,
        )
        vector = np_mod.asarray(embedding).astype("float32")
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


def describe_retriever_config(obj: object) -> dict[str, object]:
    """Return a best-effort snapshot of retriever configuration for logging."""

    index_path = getattr(obj, "index_path", None)
    if isinstance(index_path, Path):
        index_path = str(index_path)
    return {
        "index_path": index_path,
        "model_name": getattr(obj, "model_name", None),
        "backend": getattr(obj, "backend", None),
        "backend_source": getattr(obj, "backend_source", None),
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
    "describe_retriever_config",
]
