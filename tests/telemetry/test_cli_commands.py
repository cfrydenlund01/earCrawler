import json
from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli.__main__ import cli
from earCrawler.telemetry import config
from earCrawler.telemetry.events import crash_report


def prepare(tmp_path, monkeypatch):
    cfg_path = tmp_path / "telemetry.json"
    monkeypatch.setenv("EAR_TELEMETRY_CONFIG", str(cfg_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("EAR_NO_TELEM_HTTP", "1")
    return cfg_path


def test_cli_enable_disable_status(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    runner = CliRunner()
    env = {"EARCTL_USER": "test_operator"}

    res = runner.invoke(cli, ["telemetry", "status"], env=env)
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["enabled"] is False

    enabled = runner.invoke(cli, ["telemetry", "enable"], env=env)
    assert enabled.exit_code == 0, enabled.output
    cfg = config.load_config()
    assert cfg.enabled is True

    out = runner.invoke(cli, ["telemetry", "test"], env=env)
    assert out.exit_code == 0, out.output
    path = Path(out.output.strip())
    assert path.exists()

    try:
        runner.invoke(cli, ["crash-test"], env=env, catch_exceptions=False)
    except RuntimeError:
        pass
    lines = path.read_text().strip().splitlines()
    assert any(json.loads(l)["event"] == "crash_report" for l in lines)

    disabled = runner.invoke(cli, ["telemetry", "disable"], env=env)
    assert disabled.exit_code == 0, disabled.output
    cfg = config.load_config()
    assert cfg.enabled is False
