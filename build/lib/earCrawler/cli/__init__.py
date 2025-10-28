from __future__ import annotations

"""CLI entrypoint exposing ``main`` for console_scripts."""

from .__main__ import cli


def main() -> None:  # pragma: no cover - thin wrapper
    cli()


__all__ = ["main", "cli"]
