"""Shared SPARQL helpers for loader modules."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
import re

_CURIE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@lru_cache(maxsize=32)
def load_sparql_template(resource_name: str) -> str:
    """Load a SPARQL template from packaged resources."""

    data = resources.files("earCrawler").joinpath("sparql", resource_name)
    with data.open("r", encoding="utf-8") as handle:
        return handle.read()


def escape_sparql_string(value: str) -> str:
    """Escape value for safe placement inside a quoted SPARQL literal."""

    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def sanitize_curie_token(value: str, *, field_name: str) -> str:
    """Validate that value is safe as a prefixed-name local token."""

    token = str(value or "").strip()
    if not _CURIE_TOKEN_RE.match(token):
        raise ValueError(f"Invalid {field_name} token for SPARQL template: {value!r}")
    return token


__all__ = [
    "escape_sparql_string",
    "load_sparql_template",
    "sanitize_curie_token",
]
