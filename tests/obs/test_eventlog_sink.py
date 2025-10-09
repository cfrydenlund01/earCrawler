from __future__ import annotations

import platform

import pytest

from earCrawler.utils.eventlog import write_event_log


def test_eventlog_noop_non_windows(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    write_event_log("test message", level="INFO")


@pytest.mark.skipif(platform.system() != "Windows", reason="requires Windows event log")
def test_eventlog_smoke_windows():  # pragma: no cover - only on CI Windows
    write_event_log("smoke", level="INFO")
