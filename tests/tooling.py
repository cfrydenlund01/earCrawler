"""Helpers for resolving external tooling paths in tests."""

from __future__ import annotations

import os
import pathlib
from typing import Tuple

import pytest


def _resolve_tool_home(env_var: str, default: pathlib.Path) -> pathlib.Path | None:
    """Return the resolved tool directory if it exists."""

    env_value = os.environ.get(env_var)
    if env_value:
        path = pathlib.Path(env_value)
        if path.exists():
            return path
    if default.exists():
        return default
    return None


def require_jena_and_fuseki(message: str) -> Tuple[pathlib.Path, pathlib.Path]:
    """Ensure Apache Jena and Fuseki homes are available, otherwise fail the test."""

    default_jena = pathlib.Path("tools") / "jena"
    default_fuseki = pathlib.Path("tools") / "fuseki"
    jena = _resolve_tool_home("JENA_HOME", default_jena)
    fuseki = _resolve_tool_home("FUSEKI_HOME", default_fuseki)
    if jena is None or fuseki is None:
        pytest.fail(message, pytrace=False)
    return jena, fuseki


__all__ = ["require_jena_and_fuseki"]
