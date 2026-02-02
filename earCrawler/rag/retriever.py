"""Lightweight RAG retriever built on FAISS and SentenceTransformers."""

from __future__ import annotations

import logging
import pickle
import json
import time
from pathlib import Path
from typing import List, Mapping, MutableMapping, Optional

from earCrawler.utils.import_guard import import_optional

SentenceTransformer = None  # type: ignore[assignment]
faiss = None  # type: ignore[assignment]

from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.rag.build_corpus import compute_corpus_digest
from earCrawler.rag.index_builder import INDEX_META_VERSION


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
    ) -> None:
        self.tradegov_client = tradegov_client
        self.fedreg_client = fedreg_client
        self.model_name = model_name
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
        try:
            self.model = SentenceTransformer(model_name)  # type: ignore[misc]
        except Exception as exc:
            raise RetrieverMisconfiguredError(
                f"Failed to load SentenceTransformer model '{model_name}'",
                metadata={"model_name": model_name},
            ) from exc
        self.index_path = Path(index_path)
        self.meta_path = self.index_path.with_suffix(".meta.json")
        self.legacy_meta_path = self.index_path.with_suffix(".pkl")
        self.logger = logging.getLogger(__name__)
        global faiss
        if faiss is None:
            try:
                faiss = import_optional("faiss", ["faiss-cpu"])
            except RuntimeError as exc:
                raise RetrieverUnavailableError(
                    str(exc), metadata={"packages": ["faiss-cpu"]}
                ) from exc
        self._faiss = faiss
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
            try:
                index = faiss_mod.read_index(str(self.index_path))
            except Exception as exc:
                raise IndexBuildRequiredError(
                    self.index_path, reason=f"unable to read index: {exc}"
                ) from exc
            IndexIDMap = getattr(faiss_mod, "IndexIDMap", None)
            if isinstance(IndexIDMap, type) and not isinstance(index, IndexIDMap):  # pragma: no cover
                index = IndexIDMap(index)
            return index
        if not allow_create:
            raise IndexMissingError(self.index_path)
        return self._create_index(dim)

    # ------------------------------------------------------------------
    def _load_metadata(self, *, allow_create: bool = False) -> List[dict]:
        if self.meta_path.exists():
            try:
                meta_obj = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise IndexBuildRequiredError(
                    self.index_path, reason=f"failed to read metadata: {exc}"
                ) from exc
            if isinstance(meta_obj, dict) and isinstance(meta_obj.get("rows"), list):
                return list(meta_obj["rows"])
            if isinstance(meta_obj, list):
                return list(meta_obj)
            raise IndexBuildRequiredError(
                self.index_path, reason="metadata rows missing or invalid"
            )
        if self.legacy_meta_path.exists():
            try:
                with self.legacy_meta_path.open("rb") as fh:
                    return pickle.load(fh)
            except Exception as exc:
                raise IndexBuildRequiredError(
                    self.index_path, reason=f"failed to read metadata: {exc}"
                ) from exc
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
        faiss_mod = self._faiss
        faiss_mod.write_index(index, str(self.index_path))

        meta_payload = {
            "schema_version": INDEX_META_VERSION,
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
        # Legacy pickle for backward compatibility with older tooling.
        with self.legacy_meta_path.open("wb") as fh:
            pickle.dump(metadata, fh)

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

        index = self._create_index(dim)
        ids = np_mod.arange(0, len(vectors))
        index.add_with_ids(vectors, ids)

        digest = None
        try:
            digest = compute_corpus_digest(combined)
        except Exception:
            digest = None

        self._save_index(index, combined, corpus_digest=digest)
        self.logger.info("Indexed %d documents", len(combined))

    # ------------------------------------------------------------------
    def query(self, prompt: str, k: int = 5) -> List[dict]:
        """Return top ``k`` documents matching ``prompt``."""
        if not self.index_path.exists():
            raise IndexMissingError(self.index_path)
        if not (self.meta_path.exists() or self.legacy_meta_path.exists()):
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
        dim = vector.shape[1]

        index = self._load_index(dim)
        metadata = self._load_metadata()
        index_size_raw = getattr(index, "ntotal", None)
        try:
            index_size = int(index_size_raw) if index_size_raw is not None else None
        except Exception:
            index_size = None
        if index_size is not None and index_size > 0 and index_size != len(metadata):
            raise IndexBuildRequiredError(
                self.index_path, reason="index/meta size mismatch"
            )
        distances, indices = index.search(vector, k)
        results: List[dict] = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            if 0 <= idx < len(metadata):
                doc = dict(metadata[idx])
                if "section_id" not in doc and doc.get("doc_id"):
                    doc["section_id"] = str(doc.get("doc_id")).split("#", 1)[0]
                if "score" not in doc:
                    try:
                        doc["score"] = float(1.0 / (1.0 + float(distance)))
                    except Exception:
                        doc["score"] = 0.0
                results.append(doc)
        return results


def describe_retriever_config(obj: object) -> dict[str, object]:
    """Return a best-effort snapshot of retriever configuration for logging."""

    index_path = getattr(obj, "index_path", None)
    if isinstance(index_path, Path):
        index_path = str(index_path)
    return {
        "index_path": index_path,
        "model_name": getattr(obj, "model_name", None),
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
