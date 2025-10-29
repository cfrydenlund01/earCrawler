from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli.jobs import jobs, _logs_dir


def test_jobs_run_tradegov(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRADEGOV_MAX_CALLS", "10")
    monkeypatch.setenv("FR_MAX_CALLS", "10")
    monkeypatch.setenv("EARCTL_USER", "test_operator")
    policy_path = Path(__file__).resolve().parents[3] / "earCrawler" / "security" / "policy.yml"
    monkeypatch.setenv("EARCTL_POLICY_PATH", str(policy_path))

    run_dir = tmp_path / "run/logs"
    monkeypatch.setattr("earCrawler.cli.jobs._logs_dir", lambda: run_dir)

    class DummyCompleted:
        def __init__(self):
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    monkeypatch.setattr("earCrawler.cli.jobs._run_cli", lambda args, quiet: DummyCompleted())

    runner = CliRunner()
    result = runner.invoke(jobs, ["run", "tradegov", "--dry-run", "--quiet"])
    assert result.exit_code == 0
    summaries = list(run_dir.glob("*.json"))
    assert summaries, "summary file should be created"
