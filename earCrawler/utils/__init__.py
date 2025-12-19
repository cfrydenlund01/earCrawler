"""Utility helpers for earCrawler."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["budget", "diff_reports", "kg_state"]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name in __all__:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + __all__))
