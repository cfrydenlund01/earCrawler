from __future__ import annotations

"""Legacy CLI compatibility package.

Authoritative CLI entrypoints live under ``earCrawler.cli`` / ``earctl``.
"""

from earCrawler.cli.__main__ import cli

__all__ = ["cli"]
