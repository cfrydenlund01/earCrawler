from __future__ import annotations

"""Service and API registrar."""

import importlib

import click

from earCrawler.cli.api_service import api as api_cmd


def register_service_commands(root: click.Group) -> None:
    """Register service/API operations on the root CLI."""

    jobs_cli = importlib.import_module("earCrawler.cli.jobs")
    root.add_command(api_cmd, name="api")
    root.add_command(jobs_cli.jobs, name="jobs")
