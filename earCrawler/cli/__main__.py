from __future__ import annotations

"""Top-level CLI entrypoint and command registration orchestration."""

import importlib
import json
import platform
import sys
from pathlib import Path

import click

from earCrawler import __version__
from earCrawler.cli import perf, reports_cli
from earCrawler.cli.audit import audit
from earCrawler.cli.auth import auth
from earCrawler.cli.gc import gc
from earCrawler.cli.policy_cmd import policy_cmd
from earCrawler.cli.telemetry import crash_test, telemetry
from earCrawler.cli.corpus_commands import register_corpus_commands
from earCrawler.cli.eval_commands import register_eval_commands
from earCrawler.cli.kg_commands import register_kg_commands
from earCrawler.cli.rag_commands import register_rag_commands
from earCrawler.cli.service_commands import register_service_commands
from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.security import policy
from earCrawler.telemetry.hooks import install as install_telem
from earCrawler.cli import kg_commands, rag_commands

try:  # optional
    from earCrawler.cli import reconcile_cmd
except Exception:  # pragma: no cover
    reconcile_cmd = None

# Backward-compatibility symbols used in tests that monkeypatch __main__.
kg_query = kg_commands.kg_query
SPARQLClient = kg_commands.SPARQLClient
build_snapshot_index_bundle = rag_commands.build_snapshot_index_bundle

install_telem()


@click.group()
@click.version_option(__version__)
def cli() -> None:  # pragma: no cover - simple wrapper
    """earCrawler command line."""


@cli.command()
@policy.require_role("reader")
@policy.enforce
def diagnose() -> None:
    """Print deterministic diagnostic information."""

    from earCrawler.telemetry import config as tconfig

    telemetry_cfg = tconfig.load_config()
    llm_cfg = get_llm_config()
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "earCrawler": __version__,
        "telemetry": {
            "enabled": telemetry_cfg.enabled,
            "spool_dir": telemetry_cfg.spool_dir,
            "files": (
                len(list(Path(telemetry_cfg.spool_dir).glob("*")))
                if telemetry_cfg.enabled
                else 0
            ),
        },
        "llm": {
            "remote_policy": llm_cfg.remote_policy,
            "enable_remote_flag": llm_cfg.enable_remote_flag,
            "remote_enabled": llm_cfg.enable_remote,
            "remote_disabled_reason": llm_cfg.remote_disabled_reason,
            "provider": llm_cfg.provider.provider,
            "model": llm_cfg.provider.model,
        },
    }
    click.echo(json.dumps(info, sort_keys=True, indent=2))


def _register_shared_commands(root: click.Group) -> None:
    """Register non-domain command groups kept outside the phase-3 split."""

    root.add_command(reports_cli.reports, name="reports")
    root.add_command(telemetry)
    root.add_command(crash_test)
    root.add_command(gc)
    if reconcile_cmd is not None:
        root.add_command(reconcile_cmd.reconcile, name="reconcile")
    root.add_command(auth)
    root.add_command(policy_cmd, name="policy")
    root.add_command(audit)
    root.add_command(perf.perf, name="perf")

    bundle_cli = importlib.import_module("earCrawler.cli.bundle")
    root.add_command(bundle_cli.bundle, name="bundle")
    integrity_cli = importlib.import_module("earCrawler.cli.integrity")
    root.add_command(integrity_cli.integrity, name="integrity")


register_corpus_commands(cli)
register_kg_commands(cli)
register_rag_commands(cli)
register_eval_commands(cli)
register_service_commands(cli)
_register_shared_commands(cli)


def main() -> None:  # pragma: no cover - CLI entrypoint
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
