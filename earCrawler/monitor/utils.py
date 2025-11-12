"""Normalization and hashing helpers for upstream monitoring."""

from __future__ import annotations

from typing import Any
import json
import hashlib
import re


def _strip_html(text: str) -> str:
    """Return ``text`` with HTML tags removed and whitespace normalized."""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return " ".join(no_tags.split())


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, str):
        return _strip_html(value)
    return value


def normalize_json(data: Any) -> str:
    """Return a deterministic JSON string with keys sorted."""
    normalized = _normalize(data)
    return json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def stable_hash(data: Any) -> str:
    """Return SHA-256 hash of normalized ``data``."""
    norm = normalize_json(data)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
