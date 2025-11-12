from __future__ import annotations

import os
import time
from pathlib import Path

from earCrawler.utils import retention


def _touch(path: Path, size: int, age_days: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(b"0" * size)
    ts = time.time() - age_days * 86400
    os.utime(path, (ts, ts))


def test_dry_run_and_whitelist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "APP"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "PROG"))
    spool = Path(os.getenv("APPDATA")) / "EarCrawler" / "spool"
    old_file = spool / "old.log.gz"
    large_file = spool / "large.log.gz"
    recent_file = spool / "recent.log.gz"
    _touch(old_file, 100, 40)
    _touch(large_file, 9 * 1024 * 1024, 1)
    _touch(recent_file, 100, 1)

    report = retention.run_gc(
        target="telemetry",
        dry_run=True,
        max_days=30,
        max_total_mb=256,
        keep_last_n=1,
    )
    reasons = {Path(c["path"]).name: c["reason"] for c in report["candidates"]}
    assert reasons["old.log.gz"] == "age"
    assert reasons["large.log.gz"] == "size"
    assert "recent.log.gz" not in reasons

    outside = tmp_path / "other" / "bad.txt"
    _touch(outside, 10, 40)
    res = retention.gc_paths(
        [outside], retention.RetentionPolicy(max_days=1), dry_run=True
    )
    assert res["errors"]


def test_apply_deletes_and_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "APP"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "PROG"))
    spool = Path(os.getenv("APPDATA")) / "EarCrawler" / "spool"
    victim = spool / "victim.log.gz"
    _touch(victim, 100, 40)

    report = retention.run_gc(target="telemetry", dry_run=False, keep_last_n=0)
    assert not victim.exists()
    assert report["deleted"]
    audit = list((Path("kg") / "reports").glob("gc-audit-*.json"))
    assert audit
