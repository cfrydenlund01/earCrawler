from __future__ import annotations

import atexit
import sys
import time
from typing import Callable

from .config import load_config
from .events import cli_run, crash_report
from .sink_file import FileSink

_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    start = time.time()
    command = " ".join(sys.argv[1:]) or "(none)"
    cfg = load_config()
    sink = FileSink(cfg)

    old_exit = sys.exit
    old_hook = sys.excepthook

    def _coerce_exit_code(value: object) -> int:
        if isinstance(value, int):
            return value
        if value is None:
            return 0
        return 1

    def _exit(code: object = 0) -> None:
        sys._exit_code = _coerce_exit_code(code)
        old_exit(code)

    def _handle(exc_type, exc, tb):
        if cfg.enabled:
            sink.write(crash_report(command, exc_type.__name__))
        old_hook(exc_type, exc, tb)

    def _flush() -> None:
        if cfg.enabled:
            duration = int((time.time() - start) * 1000)
            code = int(getattr(sys, "_exit_code", 0))
            sink.write(cli_run(command, duration, code))

    sys.exit = _exit  # type: ignore[assignment]
    sys.excepthook = _handle  # type: ignore[assignment]
    atexit.register(_flush)
