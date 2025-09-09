from __future__ import annotations

import sys
import click

from earCrawler.security import cred_store, policy


@click.group()
@policy.require_role("admin")
def auth() -> None:
    """Manage secrets in Windows Credential Manager."""


@auth.command(name="set-secret")
@click.option("--name", required=True)
@click.option("--from-stdin", is_flag=True, required=True)
@policy.enforce
def set_secret(name: str, from_stdin: bool) -> None:
    """Store a secret read from stdin."""
    value = sys.stdin.read().strip()
    cred_store.set_secret(name, value)
    click.echo("secret stored")


@auth.command(name="delete-secret")
@click.option("--name", required=True)
@policy.enforce
def delete_secret(name: str) -> None:
    cred_store.delete_secret(name)
    click.echo("secret deleted")


@auth.command(name="list")
@policy.enforce
def list_secrets() -> None:
    names = cred_store.list_secrets()
    for n in names:
        click.echo(n)
