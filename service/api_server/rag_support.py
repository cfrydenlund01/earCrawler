from __future__ import annotations

"""Helpers for the RAG endpoint (cache + retriever loader)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)


class RetrieverProtocol(Protocol):
    """Minimal protocol implemented by the vector retriever."""

    def query(self, prompt: str, k: int = 5) -> list[dict]:
        ...


class NullRetriever:
    """Fallback retriever returning no results when FAISS/model deps are unavailable."""

    def query(self, prompt: str, k: int = 5) -> list[dict]:  # pragma: no cover - trivial
        logger.debug("NullRetriever returning empty set for query=%s", prompt)
        return []


def load_retriever() -> RetrieverProtocol:
    """Return a retriever instance when enabled, else a no-op stub.

    The actual FAISS-backed retriever is heavy (SentenceTransformers + FAISS), so we only
    instantiate it when the operator explicitly opts-in via the
    ``EARCRAWLER_API_ENABLE_RAG`` environment variable. Otherwise we return a stub to keep
    API startup + tests fast and network free.
    """

    enabled = os.getenv("EARCRAWLER_API_ENABLE_RAG", "0") == "1"
    if not enabled:
        logger.info("RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1 to enable")
        return NullRetriever()

    try:
        from api_clients.tradegov_client import TradeGovClient
        from api_clients.federalregister_client import FederalRegisterClient
        from earCrawler.rag.retriever import Retriever
    except Exception as exc:  # pragma: no cover - import errors handled gracefully
        logger.warning("Failed to import retriever dependencies: %s", exc)
        return NullRetriever()

    try:
        return Retriever(TradeGovClient(), FederalRegisterClient())
    except Exception as exc:  # pragma: no cover - heavy deps may fail at runtime
        logger.error("Unable to initialize retriever; falling back to stub: %s", exc)
        return NullRetriever()


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


__all__ = ["RetrieverProtocol", "RagQueryCache", "load_retriever"]
