from __future__ import annotations

import warnings
from datetime import datetime, timezone

from earCrawler.telemetry.config import TelemetryConfig
from earCrawler.telemetry.events import cli_run
from earCrawler.telemetry.sink_file import FileSink


def test_timestamp_utc(tmp_path):
    cfg = TelemetryConfig(enabled=True, spool_dir=str(tmp_path))
    sink = FileSink(cfg)
    with warnings.catch_warnings(record=True) as w:
        sink.write(cli_run("cmd", 0, 0))
    assert not w
    ev = sink.tail(1)[0]
    ts = ev["ts"]
    assert ts.endswith("Z")
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo == timezone.utc
