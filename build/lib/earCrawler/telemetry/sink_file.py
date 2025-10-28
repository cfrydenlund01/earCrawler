from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from .config import TelemetryConfig
from .redaction import redact


class FileSink:
    """Write telemetry events to a local JSONL spool with rotation and GC."""

    def __init__(self, cfg: TelemetryConfig):
        self.cfg = cfg
        self.dir = Path(cfg.spool_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.current = self.dir / "current.jsonl"

    def write(self, event: Dict[str, Any]) -> Path:
        event = redact(event)
        line = json.dumps(event, sort_keys=True)
        with self.current.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        if self.current.stat().st_size > self.cfg.max_file_mb * 1024 * 1024:
            self._rotate()
        self._gc()
        return self.current

    def _rotate(self) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = self.dir / f"events-{ts}.jsonl"
        self.current.replace(dest)
        gz = dest.with_suffix(dest.suffix + ".gz")
        with dest.open("rb") as f_in, gzip.open(gz, "wb") as f_out:
            f_out.writelines(f_in)
        dest.unlink(missing_ok=True)
        self.current = self.dir / "current.jsonl"

    def _gc(self) -> None:
        files = sorted(self.dir.glob("events-*.jsonl.gz"), key=lambda p: p.stat().st_mtime)
        max_total = self.cfg.max_spool_mb * 1024 * 1024
        total = sum(p.stat().st_size for p in files)
        now = time.time()
        max_age = self.cfg.max_age_days * 86400
        max_size = self.cfg.max_file_mb * 1024 * 1024

        # Remove files violating age or size limits if over quotas
        for p in list(files):
            if total <= max_total and len(files) <= self.cfg.keep_last_n:
                break
            if now - p.stat().st_mtime > max_age or p.stat().st_size > max_size:
                total -= p.stat().st_size
                files.remove(p)
                p.unlink(missing_ok=True)

        # Enforce total size and keep_last_n (oldest first)
        while (total > max_total or len(files) > self.cfg.keep_last_n) and files:
            p = files.pop(0)
            total -= p.stat().st_size
            p.unlink(missing_ok=True)

    def tail(self, n: int = 5) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if self.current.exists():
            with self.current.open("r", encoding="utf-8") as fh:
                lines = fh.readlines()[-n:]
            for line in lines:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    def compact(self) -> None:
        """Truncate empty files and gzip any stray rotated logs."""
        if self.current.exists() and self.current.stat().st_size == 0:
            self.current.unlink()
        for p in self.dir.glob("events-*.jsonl"):
            gz = p.with_suffix(p.suffix + ".gz")
            with p.open("rb") as f_in, gzip.open(gz, "wb") as f_out:
                f_out.writelines(f_in)
            p.unlink(missing_ok=True)
