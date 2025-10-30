from __future__ import annotations

import json
from click.testing import CliRunner

from earCrawler.cli import cli


def test_policy_whoami():
    runner = CliRunner()
    res = runner.invoke(cli, ["policy", "whoami"], env={"EARCTL_USER": "test_reader"})
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert set(data.keys()) == {"user", "roles", "via_token"}
    assert "EARCTL_AUTH_TOKEN" not in res.output


def test_policy_whoami_operator():
    runner = CliRunner()
    res = runner.invoke(cli, ["policy", "whoami"], env={"EARCTL_USER": "test_operator"})
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["user"] == "test_operator"
    assert "operator" in data["roles"]
