from __future__ import annotations

import json
import shlex
import click

from earCrawler.security import identity, policy


@click.group()
@policy.require_role("reader")
def policy_cmd() -> None:
    """Inspect policy and identity."""


@policy_cmd.command(name="whoami")
@policy.enforce
def whoami_cmd() -> None:
    info = identity.whoami()
    click.echo(json.dumps(info))


@policy_cmd.command(name="test")
@click.option("--command", required=True)
@policy.enforce
def test_cmd(command: str) -> None:
    tokens = shlex.split(command)
    if not tokens:
        raise click.UsageError("empty command")
    pol = policy.load_policy()
    ident = identity.whoami()
    cmd = tokens[0]
    allowed, msg = pol.check_access(ident["user"], cmd, None)
    click.echo(json.dumps({"allowed": allowed, "message": msg}))
