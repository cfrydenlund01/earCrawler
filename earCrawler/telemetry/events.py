from __future__ import annotations

import platform
import time
from typing import Any, Dict

from earCrawler import __version__
from .config import load_config


def _base(event: str) -> Dict[str, Any]:
    cfg = load_config()
    return {
        "event": event,
        "ts": int(time.time()),
        "version": __version__,
        "os": platform.platform(),
        "python": platform.python_version(),
        "device_id": cfg.device_id,
    }


def cli_run(command: str, duration_ms: int, exit_code: int) -> Dict[str, Any]:
    ev = _base("cli_run")
    ev.update({"command": command, "duration_ms": int(duration_ms), "exit_code": int(exit_code)})
    return ev


def crash_report(command: str, error: str) -> Dict[str, Any]:
    ev = _base("crash_report")
    ev.update({"command": command, "error": error, "exit_code": 1})
    return ev


def http_error_summary(command: str, count: int) -> Dict[str, Any]:
    ev = _base("http_error_summary")
    ev.update({"command": command, "duration_ms": 0, "exit_code": 0, "error": str(count)})
    return ev
