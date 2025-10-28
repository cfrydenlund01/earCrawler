from __future__ import annotations

"""Helpers for watchdog scripts to restart services and capture repro data."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(slots=True)
class WatchdogPlan:
    missing: list[str]
    restart_commands: list[list[str]]
    report_path: Path


def create_watchdog_plan(
    processes: Mapping[str, Mapping[str, object]],
    *,
    report_dir: Path,
    timestamp: datetime | None = None,
) -> WatchdogPlan:
    """Construct a restart plan and write a minimal repro report."""

    report_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc)
    missing: list[str] = []
    restart_commands: list[list[str]] = []
    lines: list[str] = [f"watchdog captured at {ts.isoformat()}"]
    for name, meta in processes.items():
        running = bool(meta.get("running", False))
        if running:
            lines.append(f"{name}: running")
            continue
        missing.append(name)
        lines.append(f"{name}: stopped")
        tail: Iterable[str] = meta.get("log_tail", [])  # type: ignore[assignment]
        if tail:
            lines.append("last_log_lines:")
            for entry in tail:
                lines.append(f"  {entry}")
        restart = list(meta.get("restart", []))  # type: ignore[arg-type]
        if restart:
            restart_commands.append(restart)
    suffix = ts.strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"watchdog-{suffix}.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return WatchdogPlan(missing=missing, restart_commands=restart_commands, report_path=report_path)


__all__ = ["WatchdogPlan", "create_watchdog_plan"]
