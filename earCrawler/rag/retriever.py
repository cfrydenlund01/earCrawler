"""Lightweight RAG retriever built on FAISS and SentenceTransformers."""

from __future__ import annotations

# Load API keys from Windows Credential Store—never hard-code.
# Secure your FAISS index path and model files.

import logging
import pickle
import time
from pathlib import Path
from typing import List

from earCrawler.utils.import_guard import import_optional

SentenceTransformer = None  # type: ignore[assignment]
faiss = None  # type: ignore[assignment]

from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient


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
        global SentenceTransformer
        if SentenceTransformer is None:
            sentence_transformers = import_optional(
                "sentence_transformers", ["sentence-transformers"]
            )
            SentenceTransformer = sentence_transformers.SentenceTransformer
        self.model = SentenceTransformer(model_name)  # type: ignore[misc]
        self.index_path = Path(index_path)
        self.meta_path = self.index_path.with_suffix(".pkl")
        self.logger = logging.getLogger(__name__)
        global faiss
        if faiss is None:
            faiss = import_optional("faiss", ["faiss-cpu"])
        self._faiss = faiss
        self._np = import_optional("numpy", ["numpy"])

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
    def _load_index(self, dim: int):
        faiss = self._faiss
        if self.index_path.exists():
            index = faiss.read_index(str(self.index_path))
            if not isinstance(index, faiss.IndexIDMap):  # pragma: no cover
                index = faiss.IndexIDMap(index)
            return index
        base = faiss.IndexFlatL2(dim)
        return faiss.IndexIDMap(base)

    # ------------------------------------------------------------------
    def _load_metadata(self) -> List[dict]:
        if self.meta_path.exists():
            with self.meta_path.open("rb") as fh:
                return pickle.load(fh)
        return []

    # ------------------------------------------------------------------
    def _save_index(
        self,
        index,
        metadata: List[dict],
    ) -> None:
        faiss = self._faiss
        faiss.write_index(index, str(self.index_path))
        with self.meta_path.open("wb") as fh:
            pickle.dump(metadata, fh)

    # ------------------------------------------------------------------
    def add_documents(self, docs: List[dict]) -> None:
        """Add ``docs`` to the FAISS index.

        Parameters
        ----------
        docs:
            List of document dictionaries. Text is taken from ``text``,
            ``body``, ``summary`` or ``title`` fields.
        """
        if not docs:
            self.logger.info("No documents provided for indexing")
            return

        texts = []
        for d in docs:
            text = (
                d.get("text")
                or d.get("body")
                or d.get("summary")
                or d.get("title")
                or ""
            )
            texts.append(str(text))

        np = self._np
        vectors = self._retry(
            self.model.encode,
            texts,
            show_progress_bar=False,
        )
        vectors = np.asarray(vectors).astype("float32")
        dim = vectors.shape[1]

        index = self._load_index(dim)
        metadata = self._load_metadata()
        start_id = len(metadata)
        ids = np.arange(start_id, start_id + len(vectors))
        index.add_with_ids(vectors, ids)
        metadata.extend(docs)

        self._save_index(index, metadata)
        self.logger.info("Indexed %d documents", len(docs))

    # ------------------------------------------------------------------
    def query(self, prompt: str, k: int = 5) -> List[dict]:
        """Return top ``k`` documents matching ``prompt``."""
        if not self.index_path.exists():
            self.logger.warning("Index file %s not found", self.index_path)
            return []
        np = self._np
        embedding = self._retry(
            self.model.encode,
            [prompt],
            show_progress_bar=False,
        )
        vector = np.asarray(embedding).astype("float32")
        dim = vector.shape[1]

        index = self._load_index(dim)
        metadata = self._load_metadata()
        distances, indices = index.search(vector, k)
        results: List[dict] = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            if 0 <= idx < len(metadata):
                doc = dict(metadata[idx])
                if "score" not in doc:
                    try:
                        doc["score"] = float(1.0 / (1.0 + float(distance)))
                    except Exception:
                        doc["score"] = 0.0
                results.append(doc)
        return results
