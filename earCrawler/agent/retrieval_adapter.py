"""Adapters to bridge RAG retrievers to the Mistral agent interfaces."""

from __future__ import annotations

from typing import Iterable, List, Mapping, Sequence


class TextContextRetriever:
    """Wraps a metadata-rich retriever and returns plain text contexts.

    The Mistral agent expects ``List[str]`` contexts, whereas the FAISS-backed
    retriever returns ``List[dict]`` with multiple possible text-bearing keys.
    This adapter extracts the first non-empty value from a prioritized list of
    keys and discards empty contexts.
    """

    _PREFERRED_FIELDS: Sequence[str] = (
        "text",
        "body",
        "content",
        "paragraph",
        "summary",
        "snippet",
        "title",
    )

    def __init__(self, retriever: object) -> None:
        self._retriever = retriever
        self.last_documents: list[dict] = []
        self.last_contexts: List[str] = []

    def _extract_contexts(self, docs: Iterable[Mapping[str, object]]) -> List[str]:
        contexts: List[str] = []
        for doc in docs:
            for field in self._PREFERRED_FIELDS:
                value = doc.get(field)
                if value:
                    text = str(value).strip()
                    if text:
                        contexts.append(text)
                        break
        return contexts

    def select_contexts(self, documents: Iterable[Mapping[str, object]]) -> List[str]:
        """Convert raw document dicts into plain-text contexts."""

        return self._extract_contexts(documents)

    def query(self, query: str, k: int = 5) -> List[str]:
        documents = self._retriever.query(query, k=k)
        self.last_documents = list(documents or [])
        self.last_contexts = self._extract_contexts(self.last_documents)
        return list(self.last_contexts)


__all__ = ["TextContextRetriever"]
