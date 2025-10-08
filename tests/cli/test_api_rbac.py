from __future__ import annotations

from click.testing import CliRunner

from earCrawler.cli import cli


def invoke(args: list[str], user: str) -> int:
    runner = CliRunner()
    result = runner.invoke(cli, args, env={"EARCTL_USER": user})
    return result.exit_code


def test_api_commands_require_roles() -> None:
    assert invoke(["api", "start"], "test_operator") == 0
    assert invoke(["api", "start"], "test_maintainer") == 0
    assert invoke(["api", "start"], "test_reader") != 0
    assert invoke(["api", "stop"], "test_operator") == 0
    assert invoke(["api", "smoke"], "test_operator") == 0
