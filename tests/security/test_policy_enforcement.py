from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli import cli
from earCrawler.security import identity, policy


def _invoke(cmd: str, user: str):
    runner = CliRunner()
    return runner.invoke(cli, cmd.split(), env={"EARCTL_USER": user})


def test_policy_matrix():
    matrix = [
        ("diagnose", "test_reader", 0),
        ("gc --dry-run", "test_reader", 1),
        ("gc --dry-run", "test_operator", 0),
        ("policy whoami", "test_reader", 0),
        ("policy whoami", "test_operator", 0),
    ]
    for cmd, user, code in matrix:
        res = _invoke(cmd, user)
        assert res.exit_code == code


def test_identity_env_override_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES", raising=False)
    monkeypatch.setenv("EARCTL_USER", "test_admin")
    monkeypatch.setattr("earCrawler.security.identity.getpass.getuser", lambda: "localuser")

    info = identity.whoami()

    assert info["user"] == "localuser"
    assert "admin" not in info["roles"]


def test_policy_path_env_override_requires_explicit_opt_in(monkeypatch, tmp_path: Path) -> None:
    custom_policy = tmp_path / "policy.yml"
    custom_policy.write_text(
        "roles:\n"
        "  admin: ['*']\n"
        "commands:\n"
        "  sentinel: ['admin']\n"
        "overrides:\n"
        "  default:\n"
        "    roles: ['admin']\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EARCTL_POLICY_PATH", str(custom_policy))
    monkeypatch.delenv("EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES", raising=False)
    locked = policy.load_policy()
    assert "sentinel" not in locked.commands

    monkeypatch.setenv("EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES", "1")
    unsafe = policy.load_policy()
    assert "sentinel" in unsafe.commands
