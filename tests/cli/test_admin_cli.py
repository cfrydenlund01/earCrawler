from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli.admin import admin


def _allow_operator(monkeypatch) -> None:
    monkeypatch.setenv("EARCTL_USER", "test_operator")
    policy_path = Path(__file__).resolve().parents[3] / "earCrawler" / "security" / "policy.yml"
    monkeypatch.setenv("EARCTL_POLICY_PATH", str(policy_path))


def test_admin_stats_writes_run_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _allow_operator(monkeypatch)
    run_dir = tmp_path / "run" / "logs"
    monkeypatch.setattr("earCrawler.cli.admin._logs_dir", lambda: run_dir)

    class DummyBench:
        timings = {"load_ttl": 0.1}

        def to_json(self) -> str:
            return '{"timings":{"load_ttl":0.1}}'

    monkeypatch.setattr("earCrawler.cli.admin.run_benchmarks", lambda fixtures, iterations: DummyBench())

    runner = CliRunner()
    result = runner.invoke(admin, ["stats", "--iterations", "1"])
    assert result.exit_code == 0

    summaries = list(run_dir.glob("admin-stats-*.json"))
    assert summaries, "run summary should be emitted"
    data = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    step_names = [step["name"] for step in data["steps"]]
    assert "benchmarks" in step_names
    assert "write-output" in step_names


def test_admin_export_writes_run_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _allow_operator(monkeypatch)
    run_dir = tmp_path / "run" / "logs"
    monkeypatch.setattr("earCrawler.cli.admin._logs_dir", lambda: run_dir)

    ttl = tmp_path / "kg" / "ear.ttl"
    ttl.parent.mkdir(parents=True, exist_ok=True)
    ttl.write_text("@prefix : <https://example.com/> .", encoding="utf-8")

    def fake_export_profiles(ttl_path: Path, out_dir: Path, *, stem: str):
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = [{"path": str(out_dir / f"{stem}.ttl")}]
        return manifest

    monkeypatch.setattr("earCrawler.cli.admin.export_profiles", fake_export_profiles)

    runner = CliRunner()
    result = runner.invoke(
        admin,
        [
            "export",
            "--ttl",
            str(ttl),
            "--out",
            str(tmp_path / "dist" / "exports"),
            "--stem",
            "dataset",
        ],
    )
    assert result.exit_code == 0

    summaries = list(run_dir.glob("admin-export-*.json"))
    assert summaries, "run summary should be emitted"
    data = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert any(step["name"] == "export-profiles" for step in data["steps"])
