from __future__ import annotations

"""Free-text redaction helpers for corpus paragraphs."""

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_RE = re.compile(r"(?:bearer\s+)?[A-Za-z0-9\-_=]{20,}", re.IGNORECASE)
PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\[^\s]+|\\\\[^\s]+|~/[^\s]+|(?<![A-Za-z0-9:/])/(?!/)[^\s]+)"
)
URL_QUERY_RE = re.compile(r"https?://[^\s?]+(?:\?[^\s#]+)")
GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}"
)
PHONE_RE = re.compile(
    r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _strip_query(url: str) -> str:
    base, _, _ = url.partition("?")
    base, _, _ = base.partition("#")
    return base


def scrub_text(text: str) -> str:
    """Apply conservative PII scrubbing to free-form ``text``."""

    if not text:
        return ""

    value = text
    value = EMAIL_RE.sub("[redacted]", value)
    value = GUID_RE.sub("[guid]", value)
    value = TOKEN_RE.sub("[token]", value)
    value = URL_QUERY_RE.sub(lambda m: _strip_query(m.group(0)), value)
    value = PATH_RE.sub("[path]", value)
    value = PHONE_RE.sub("[phone]", value)
    value = SSN_RE.sub("[ssn]", value)
    # Collapse whitespace introduced by replacements for deterministic hashing.
    return " ".join(value.split())


__all__ = ["scrub_text"]
