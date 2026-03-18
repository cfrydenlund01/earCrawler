from __future__ import annotations

"""Legacy CLI compatibility wrappers."""

import click

LEGACY_CLI_PREFIX = "Legacy top-level CLI wrapper:"


def _warn(message: str) -> None:
    click.echo(f"{LEGACY_CLI_PREFIX} {message}", err=True)


def kg_validate_main() -> None:
    """Compatibility entrypoint for the legacy ``kg-validate`` script."""

    _warn("use `earctl kg validate` or `py -m earCrawler.cli kg validate`.")
    from earCrawler.cli.kg_commands import kg_validate

    kg_validate.main(prog_name="kg-validate", standalone_mode=True)


def kg_emit_main() -> None:
    """Compatibility entrypoint for the legacy ``cli.kg_emit`` module."""

    _warn("use `earctl kg emit` or `py -m earCrawler.cli kg emit`.")
    from earCrawler.cli.kg_commands import kg_emit

    kg_emit.main(prog_name="cli.kg_emit", standalone_mode=True)
