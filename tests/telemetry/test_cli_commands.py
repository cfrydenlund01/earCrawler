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
    res = runner.invoke(cli, ["telemetry", "status"])
    data = json.loads(res.output)
    assert data["enabled"] is False

    runner.invoke(cli, ["telemetry", "enable"])
    cfg = config.load_config()
    assert cfg.enabled is True

    out = runner.invoke(cli, ["telemetry", "test"])
    path = Path(out.output.strip())
    assert path.exists()

    try:
        runner.invoke(cli, ["crash-test"], catch_exceptions=False)
    except RuntimeError:
        pass
    lines = path.read_text().strip().splitlines()
    assert any(json.loads(l)["event"] == "crash_report" for l in lines)

    runner.invoke(cli, ["telemetry", "disable"])
    cfg = config.load_config()
    assert cfg.enabled is False
