from __future__ import annotations

"""Retriever backend and mode resolution helpers."""

import os
import sys

RETRIEVAL_BACKEND_ENV = "EARCRAWLER_RETRIEVAL_BACKEND"
RETRIEVAL_MODE_ENV = "EARCRAWLER_RETRIEVAL_MODE"
LEGACY_PICKLE_METADATA_ENV = "EARCRAWLER_ENABLE_LEGACY_PICKLE_METADATA"

SUPPORTED_RETRIEVAL_BACKENDS = {"faiss", "bruteforce"}
SUPPORTED_RETRIEVAL_MODES = {"dense", "hybrid"}


def is_windows_platform() -> bool:
    return sys.platform.startswith("win")


def default_backend_name() -> str:
    return "bruteforce" if is_windows_platform() else "faiss"


def legacy_pickle_metadata_enabled() -> bool:
    raw = os.getenv(LEGACY_PICKLE_METADATA_ENV)
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def resolve_backend_name(
    explicit_backend: str | None = None,
) -> tuple[str, str] | tuple[None, str]:
    raw = explicit_backend
    source = "default"
    if raw is None:
        raw = os.getenv(RETRIEVAL_BACKEND_ENV)
        if raw is not None:
            source = f"env:{RETRIEVAL_BACKEND_ENV}"
    else:
        source = "argument"

    if raw is None:
        return default_backend_name(), source

    backend = str(raw).strip().lower()
    if backend not in SUPPORTED_RETRIEVAL_BACKENDS:
        return None, source
    return backend, source


def resolve_retrieval_mode(
    explicit_mode: str | None = None,
) -> tuple[str, str] | tuple[None, str]:
    raw = explicit_mode
    source = "default"
    if raw is None:
        raw = os.getenv(RETRIEVAL_MODE_ENV)
        if raw is not None:
            source = f"env:{RETRIEVAL_MODE_ENV}"
    else:
        source = "argument"

    if raw is None:
        return "dense", source

    mode = str(raw).strip().lower()
    if mode not in SUPPORTED_RETRIEVAL_MODES:
        return None, source
    return mode, source


__all__ = [
    "LEGACY_PICKLE_METADATA_ENV",
    "RETRIEVAL_BACKEND_ENV",
    "RETRIEVAL_MODE_ENV",
    "SUPPORTED_RETRIEVAL_BACKENDS",
    "SUPPORTED_RETRIEVAL_MODES",
    "default_backend_name",
    "is_windows_platform",
    "legacy_pickle_metadata_enabled",
    "resolve_backend_name",
    "resolve_retrieval_mode",
]
