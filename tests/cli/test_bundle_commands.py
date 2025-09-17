from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli import bundle as bundle_cli
from earCrawler.cli.__main__ import cli


def test_bundle_command_rbac(monkeypatch):
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_run(script: Path, *args: str) -> None:
        calls.append((script, args))

    monkeypatch.setattr(bundle_cli, "_run_ps", fake_run)

    runner = CliRunner()
    res = runner.invoke(cli, ["bundle", "build"], env={"EARCTL_USER": "test_operator"})
    assert res.exit_code == 0
    assert calls and calls[0][0].name == "build-offline-bundle.ps1"

    res = runner.invoke(cli, ["bundle", "build"], env={"EARCTL_USER": "test_reader"})
    assert res.exit_code != 0


def test_bundle_verify_and_smoke(monkeypatch, tmp_path):
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_run(script: Path, *args: str) -> None:
        calls.append((script, args))

    monkeypatch.setattr(bundle_cli, "_run_ps", fake_run)
    runner = CliRunner()
    env = {"EARCTL_USER": "test_operator"}
    bundle_dir = tmp_path / "bundle"
    scripts_dir = bundle_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    for name in ("bundle-verify.ps1", "bundle-first-run.ps1"):
        (scripts_dir / name).write_text("echo")

    res = runner.invoke(cli, ["bundle", "verify", "--path", str(bundle_dir)], env=env)
    assert res.exit_code == 0
    assert calls[0][0].name == "bundle-verify.ps1"
    assert calls[0][1] == ("-Path", str(bundle_dir))

    custom_root = tmp_path / "custom"
    custom_scripts = custom_root / "scripts"
    custom_scripts.mkdir(parents=True, exist_ok=True)
    (custom_scripts / "bundle-first-run.ps1").write_text("echo")

    res = runner.invoke(cli, ["bundle", "smoke", "--path", str(custom_root)], env=env)
    assert res.exit_code == 0
    assert calls[1][0].name == "bundle-first-run.ps1"
    assert calls[1][1] == ("-Path", str(custom_root))
