from __future__ import annotations

"""Helpers for the RAG endpoint (cache + retriever loader)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class RetrieverProtocol(Protocol):
    """Minimal protocol implemented by the vector retriever."""

    def query(self, prompt: str, k: int = 5) -> list[dict]: ...


class NullRetriever:
    """Fallback retriever representing a disabled configuration."""

    def __init__(self, *, reason: str | None = None) -> None:
        self.enabled = False
        self.ready = False
        self.failure_type = "retriever_disabled"
        self.disabled_reason = (
            reason
            or "RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1 to enable"
        )
        self.index_path: str | None = None
        self.model_name: str | None = None

    def query(
        self, prompt: str, k: int = 5
    ) -> list[dict]:  # pragma: no cover - trivial
        logger.debug("NullRetriever returning empty set for query=%s", prompt)
        return []


class BrokenRetriever:
    """Retriever placeholder that raises a stored initialization failure."""

    def __init__(
        self,
        exc: Exception,
        *,
        failure_type: str = "retriever_init_failed",
        index_path: Path | None = None,
        model_name: str | None = None,
    ) -> None:
        self.enabled = True
        self.ready = False
        self.failure = exc
        self.failure_type = failure_type
        self.index_path = str(index_path) if index_path else None
        self.model_name = model_name

    def query(self, prompt: str, k: int = 5) -> list[dict]:
        raise self.failure


def load_retriever() -> RetrieverProtocol:
    """Return a retriever instance when enabled, else a no-op stub.

    The actual FAISS-backed retriever is heavy (SentenceTransformers + FAISS), so we only
    instantiate it when the operator explicitly opts-in via the
    ``EARCRAWLER_API_ENABLE_RAG`` environment variable. Otherwise we return a stub to keep
    API startup + tests fast and network free.
    """

    enabled = os.getenv("EARCRAWLER_API_ENABLE_RAG", "0") == "1"
    if not enabled:
        reason = "RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1"
        logger.info(reason)
        return NullRetriever(reason=reason)

    try:
        from api_clients.tradegov_client import TradeGovClient
        from api_clients.federalregister_client import FederalRegisterClient
        from earCrawler.rag.retriever import (
            IndexBuildRequiredError,
            IndexMissingError,
            Retriever,
            RetrieverError,
        )
    except Exception as exc:  # pragma: no cover - import errors handled gracefully
        logger.warning("Failed to import retriever dependencies: %s", exc)
        return BrokenRetriever(exc, failure_type="retriever_import_failed")

    index_override = os.getenv("EARCRAWLER_FAISS_INDEX")
    model_override = os.getenv("EARCRAWLER_FAISS_MODEL")
    index_path = Path(index_override) if index_override else Path("data") / "faiss" / "index.faiss"
    model_name = model_override or "all-MiniLM-L12-v2"

    try:
        retriever = Retriever(
            TradeGovClient(),
            FederalRegisterClient(),
            model_name=model_name,
            index_path=index_path,
        )
        retriever.ready = True
        return retriever
    except (IndexMissingError, IndexBuildRequiredError) as exc:
        logger.error("Retriever index not ready: %s", exc)
        return BrokenRetriever(
            exc,
            failure_type=getattr(exc, "code", "index_missing"),
            index_path=index_path,
            model_name=model_name,
        )
    except RetrieverError as exc:  # pragma: no cover - typed retriever failures
        logger.error("Retriever failed to initialize: %s", exc)
        return BrokenRetriever(
            exc,
            failure_type=getattr(exc, "code", "retriever_error"),
            index_path=index_path,
            model_name=model_name,
        )
    except Exception as exc:  # pragma: no cover - heavy deps may fail at runtime
        logger.error("Unable to initialize retriever; falling back to stub: %s", exc)
        return BrokenRetriever(
            exc,
            failure_type="retriever_init_failed",
            index_path=index_path,
            model_name=model_name,
        )


@dataclass
class RagCacheEntry:
    expires_at: datetime
    payload: list[dict]


class RagQueryCache:
    """Tiny in-memory TTL cache for repeat RAG queries."""

    def __init__(self, ttl_seconds: float = 30.0, max_entries: int = 64) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._entries: dict[str, RagCacheEntry] = {}

    def get(self, key: str) -> list[dict] | None:
        entry = self._entries.get(key)
        if not entry:
            return None
        if entry.expires_at <= datetime.now(timezone.utc):
            self._entries.pop(key, None)
            return None
        return entry.payload

    def put(self, key: str, payload: list[dict]) -> datetime:
        if len(self._entries) >= self._max:
            victim = min(self._entries.items(), key=lambda item: item[1].expires_at)
            self._entries.pop(victim[0], None)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
        self._entries[key] = RagCacheEntry(expires_at=expires_at, payload=payload)
        return expires_at

    def expires_at(self, key: str) -> datetime | None:
        entry = self._entries.get(key)
        if not entry:
            return None
        if entry.expires_at <= datetime.now(timezone.utc):
            self._entries.pop(key, None)
            return None
        return entry.expires_at


__all__ = ["RetrieverProtocol", "RagQueryCache", "load_retriever", "NullRetriever", "BrokenRetriever"]
