from __future__ import annotations

"""Package metadata."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("earCrawler")
except PackageNotFoundError:  # pragma: no cover - package not installed
    __version__ = "0.9.0"

__all__ = ["__version__"]
