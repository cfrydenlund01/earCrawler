from __future__ import annotations

"""CLI entrypoint exposing ``main`` for console_scripts."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - imported for type checkers only
    from .__main__ import cli as _cli_type

__all__ = ["main", "cli"]


def __getattr__(name: str) -> Any:  # pragma: no cover - simple delegation
    if name == "cli":
        from .__main__ import cli as _cli

        return _cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover - simple delegation
    return sorted(__all__)


def main() -> None:  # pragma: no cover - thin wrapper
    from .__main__ import cli as _cli

    _cli()
