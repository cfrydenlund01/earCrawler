from __future__ import annotations

from click.testing import CliRunner

from earCrawler.cli import cli


def _invoke(cmd: str, user: str):
    runner = CliRunner()
    return runner.invoke(cli, cmd.split(), env={"EARCTL_USER": user})


def test_policy_matrix():
    matrix = [
        ("diagnose", "test_reader", 0),
        ("gc --dry-run", "test_reader", 1),
        ("gc --dry-run", "test_operator", 0),
        ("policy whoami", "test_reader", 0),
        ("policy whoami", "test_operator", 1),
    ]
    for cmd, user, code in matrix:
        res = _invoke(cmd, user)
        assert res.exit_code == code
