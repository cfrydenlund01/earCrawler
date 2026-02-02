"""Helpers to gracefully skip torch / GPU dependent tests on Windows."""

from __future__ import annotations

import os
from functools import lru_cache

import pytest


@lru_cache(maxsize=1)
def torch_import_ok() -> bool:
    """Return True when torch imports without missing DLL errors."""

    try:
        import torch  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


def require_torch_or_skip(reason: str | None = None) -> None:
    """Skip tests cleanly when torch cannot be imported."""

    if torch_import_ok():
        return
    pytest.skip(
        reason
        or "PyTorch unavailable (import failed or missing DLL); skipping CPU/GPU dependent test.",
        allow_module_level=True,
    )


def gpu_env_ok() -> bool:
    """True only when GPU tests are explicitly enabled and CUDA is usable."""

    if os.getenv("EARCRAWLER_ENABLE_GPU_TESTS") != "1":
        return False
    if not torch_import_ok():
        return False
    try:
        import torch
    except (ImportError, OSError):
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def require_gpu_or_skip(reason: str | None = None) -> None:
    """Skip tests unless the environment is opted-in and CUDA is available."""

    if gpu_env_ok():
        return
    pytest.skip(
        reason
        or "GPU-only test; set EARCRAWLER_ENABLE_GPU_TESTS=1 with a working CUDA runtime to run.",
        allow_module_level=True,
    )


__all__ = [
    "torch_import_ok",
    "require_torch_or_skip",
    "gpu_env_ok",
    "require_gpu_or_skip",
]
