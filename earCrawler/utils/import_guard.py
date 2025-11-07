"""Helpers for lazily importing optional GPU/inference dependencies."""

from __future__ import annotations

import importlib
from functools import lru_cache
from types import ModuleType
from typing import Iterable, Tuple

GPU_EXTRA = "gpu"
GPU_REQUIREMENTS_FILE = "requirements-gpu.txt"


def _format_package_list(packages: Iterable[str]) -> str:
    unique = sorted(dict.fromkeys(packages))
    return ", ".join(unique)


def raise_missing_gpu_deps(
    packages: Iterable[str],
    cause: Exception | None = None,
) -> None:
    """Raise a consistent error guiding users to the GPU extra."""

    package_list = _format_package_list(packages)
    message = (
        f"Missing optional dependency ({package_list}). "
        f"Install the GPU stack with `pip install -e .[{GPU_EXTRA}]`, "
        f"`pip install earCrawler[{GPU_EXTRA}]`, "
        f"or install the bundle defined in `{GPU_REQUIREMENTS_FILE}`."
    )
    raise RuntimeError(message) from cause


@lru_cache(maxsize=None)
def _import_cached(name: str) -> ModuleType:
    return importlib.import_module(name)


def import_optional(name: str, packages: Iterable[str]) -> ModuleType:
    """Return ``importlib.import_module(name)`` or raise a friendly error."""

    package_tuple: Tuple[str, ...] = tuple(packages)
    try:
        return _import_cached(name)
    except ImportError as exc:  # pragma: no cover - exercised via callers
        raise_missing_gpu_deps(package_tuple or (name,), exc)
