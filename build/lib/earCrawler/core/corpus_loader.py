"""Unified corpus loader abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterator, List


class CorpusLoader(ABC):
    """Abstract base class for paragraph loaders."""

    @abstractmethod
    def iterate_paragraphs(self) -> Iterator[Dict[str, object]]:
        """Yield dictionaries with ``source``, ``text`` and ``identifier``."""

    def load_paragraphs(self) -> List[Dict[str, object]]:
        """Return all paragraphs as a list."""
        return list(self.iterate_paragraphs())
