"""Mention extraction with token-aware scoring and guardrails."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


STOPWORDS = {
    "inc",
    "corp",
    "co",
    "co.",
    "company",
    "companies",
    "corporation",
    "group",
    "limited",
    "ltd",
    "llc",
    "holding",
    "holdings",
    "international",
}


TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


@dataclass(frozen=True)
class MentionScore:
    entity_id: str
    strength: float


class MentionExtractor:
    """Score entity mentions in text using token and pattern heuristics."""

    def __init__(self, *, stopwords: Iterable[str] | None = None, window: int = 8) -> None:
        self.stopwords = {s.lower() for s in (stopwords or STOPWORDS)}
        self.window = max(2, window)

    # ------------------------------------------------------------------
    # Public helpers

    def extract(self, text: str, entities: Dict[str, str]) -> Dict[str, float]:
        """Return best strength per entity for ``text``.

        Parameters
        ----------
        text:
            Passage to analyse.
        entities:
            Mapping of entity identifier -> canonical name.
        """

        scores: Dict[str, float] = {}
        for entity_id, name in entities.items():
            strength = self.score(text, name)
            if strength > 0:
                prev = scores.get(entity_id, 0.0)
                if strength > prev:
                    scores[entity_id] = strength
        return scores

    def score(self, text: str, candidate: str) -> float:
        """Score mention strength for ``candidate`` inside ``text``."""

        if not text or not candidate:
            return 0.0
        text_tokens = self._tokenize(text)
        if not text_tokens:
            return 0.0
        cand_tokens = self._tokenize(candidate)
        core_tokens = self._core_tokens(cand_tokens)
        if not core_tokens:
            return 0.0

        # Exact token sequence match (full candidate)
        if cand_tokens and self._contains_sequence(text_tokens, cand_tokens):
            return 1.0
        # Core tokens contiguous match
        if self._contains_sequence(text_tokens, core_tokens):
            return 0.85
        # Core tokens all appear in tight window
        if self._core_in_window(text_tokens, core_tokens):
            return 0.65
        # Acronym detection as a weaker signal
        acronym = "".join(tok[0] for tok in core_tokens if tok)
        if len(acronym) >= 2 and self._contains_acronym(text_tokens, acronym):
            return 0.45
        return 0.0

    # ------------------------------------------------------------------
    # Internals

    def _tokenize(self, text: str) -> List[str]:
        return [tok.lower() for tok in TOKEN_RE.findall(text or "")]

    def _core_tokens(self, tokens: Sequence[str]) -> List[str]:
        return [tok for tok in tokens if tok and tok not in self.stopwords]

    @staticmethod
    def _contains_sequence(tokens: Sequence[str], pattern: Sequence[str]) -> bool:
        if len(pattern) == 0 or len(tokens) < len(pattern):
            return False
        for idx in range(len(tokens) - len(pattern) + 1):
            if tokens[idx: idx + len(pattern)] == list(pattern):
                return True
        return False

    def _core_in_window(self, tokens: Sequence[str], core_tokens: Sequence[str]) -> bool:
        target = set(core_tokens)
        if not target:
            return False
        for start in range(len(tokens)):
            seen: set[str] = set()
            for cursor in range(start, min(len(tokens), start + self.window)):
                tok = tokens[cursor]
                if tok in target:
                    seen.add(tok)
                    if len(seen) == len(target):
                        return True
        return False

    @staticmethod
    def _contains_acronym(tokens: Sequence[str], acronym: str) -> bool:
        letters = "".join(tok[0] for tok in tokens if tok)
        return acronym.lower() in letters


__all__ = ["MentionExtractor", "MentionScore"]

