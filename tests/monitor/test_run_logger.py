from pathlib import Path

from earCrawler.monitor.run_logger import run_logger, log_step


def test_run_logger_writes_summary(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    with run_logger(path, run_id="test-run", input_hash="abc123") as run:
        with log_step(run, "step-1") as meta:
            meta["foo"] = "bar"
    data = path.read_text(encoding="utf-8")
    assert "test-run" in data
    assert "step-1" in data
