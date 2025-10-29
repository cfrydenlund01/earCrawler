"""Simple in-memory call budget tracker for API usage limits."""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from threading import Lock
from typing import Dict


class BudgetExceededError(RuntimeError):
    """Raised when a budget would be exceeded."""


_COUNTS: Dict[str, int] = defaultdict(int)
_LIMITS: Dict[str, int | None] = defaultdict(lambda: None)
_LOCK = Lock()


def set_limit(name: str, limit: int | None) -> None:
    """Set the maximum allowed calls for ``name`` (``None`` disables the limit)."""

    with _LOCK:
        _LIMITS[name] = limit
        _COUNTS[name] = 0


def reset(name: str | None = None) -> None:
    """Reset counters for ``name`` or all names when ``None``."""

    with _LOCK:
        if name is None:
            _COUNTS.clear()
        else:
            _COUNTS[name] = 0


@contextmanager
def consume(name: str, limit: int | None = None):
    """Consume one unit of budget for ``name`` enforcing ``limit`` if provided."""

    with _LOCK:
        effective_limit = limit if limit is not None else _LIMITS[name]
        if effective_limit is not None and _COUNTS[name] >= effective_limit:
            raise BudgetExceededError(f"Budget exceeded for {name}: {effective_limit}")
        _COUNTS[name] += 1
    try:
        yield
    finally:
        pass

