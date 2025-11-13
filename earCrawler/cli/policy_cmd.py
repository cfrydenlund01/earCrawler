from __future__ import annotations

import json
import shlex
from typing import Iterable, Mapping

import click

from earCrawler.security import identity, policy

_NO_ROLES_HINT = "no explicit roles (falls back to default)"


def _format_role_permissions(roles: Mapping[str, Iterable[str]]) -> list[str]:
    formatted: list[str] = []
    for role in sorted(roles):
        perms = list(roles[role] or [])
        if perms == ["*"]:
            formatted.append(f"  - {role}: full access (*)")
        elif perms:
            formatted.append(f"  - {role}: {', '.join(perms)}")
        else:
            formatted.append(f"  - {role}: no commands mapped")
    return formatted


def _format_identities(
    overrides: Mapping[str, Mapping[str, Iterable[str]]],
) -> list[str]:
    entries: list[str] = []
    for name in sorted(k for k in overrides if k != "default"):
        roles = list(overrides[name].get("roles", []))
        if roles:
            entries.append(f"  - {name}: {', '.join(roles)}")
        else:
            entries.append(f"  - {name}: {_NO_ROLES_HINT}")
    return entries


def _build_policy_help() -> str:
    base = [
        "Inspect policy and identity.",
        "",
        "Set EARCTL_USER to impersonate a configured identity before running commands,",
        "for example:",
        "  $env:EARCTL_USER = 'test_operator'",
        "Use 'policy whoami' to inspect the active identity.",
    ]
    try:
        pol = policy.load_policy()
    except Exception:  # pragma: no cover - defensive help generation
        pol = None
    if pol:
        identities = _format_identities(pol.overrides or {})
        if identities:
            base.append("")
            base.append("Built-in identities (security/policy.yml):")
            base.extend(identities)
        if pol.roles:
            base.append("")
            base.append("Role permissions:")
            base.extend(_format_role_permissions(pol.roles))
    return "\n".join(base)


_POLICY_HELP = _build_policy_help()


@click.group(help=_POLICY_HELP)
@policy.require_role("reader", "operator", "maintainer", "admin")
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
