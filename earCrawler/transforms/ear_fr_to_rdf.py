"""Utilities for extracting EAR part references from Federal Register content."""

from __future__ import annotations

import re
from typing import Iterable, List, Set

PART_PATTERN = re.compile(r"\b15\s*CFR\s*Part\s*(\d{3})\b", re.IGNORECASE)


def extract_parts_from_text(text: str) -> Set[str]:
    """Return the set of part numbers mentioned in ``text``."""

    return {match for match in PART_PATTERN.findall(text or "") if match}


def pick_parts(parts: Iterable[str] | None) -> List[str]:
    """Normalise an iterable of part numbers to a sorted list of digits only."""

    if not parts:
        return []
    filtered = {p for p in parts if p and p.isdigit()}
    return sorted(filtered)


__all__ = ["PART_PATTERN", "extract_parts_from_text", "pick_parts"]
