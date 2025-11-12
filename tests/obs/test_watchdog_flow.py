from __future__ import annotations

from datetime import datetime, timezone

from earCrawler.observability.watchdog import create_watchdog_plan


def test_watchdog_plan_writes_report(tmp_path):
    processes = {
        "api": {
            "running": False,
            "log_tail": ["error: boom"],
            "restart": ["pwsh", "-File", "scripts/api-start.ps1"],
        },
        "fuseki": {"running": True, "log_tail": []},
    }
    plan = create_watchdog_plan(
        processes,
        report_dir=tmp_path,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert plan.missing == ["api"]
    assert plan.report_path.exists()
    text = plan.report_path.read_text(encoding="utf-8")
    assert "error: boom" in text
    assert plan.restart_commands == [["pwsh", "-File", "scripts/api-start.ps1"]]
