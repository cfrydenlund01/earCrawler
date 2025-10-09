from __future__ import annotations

"""Utility to write structured summaries to the Windows Event Log."""

import logging
import platform

try:  # pragma: no cover - import guarded for non-Windows
    import ctypes
    from ctypes import wintypes
except Exception:  # pragma: no cover - handled at runtime
    ctypes = None  # type: ignore[assignment]
    wintypes = None  # type: ignore[assignment]


_EVENT_TYPES = {
    "INFO": 0x0004,  # EVENTLOG_INFORMATION_TYPE
    "WARNING": 0x0002,  # EVENTLOG_WARNING_TYPE
    "ERROR": 0x0001,  # EVENTLOG_ERROR_TYPE
}

_LOGGER = logging.getLogger("earcrawler.eventlog")


def write_event_log(message: str, *, level: str = "INFO", source: str = "EarCrawler") -> None:
    """Write an event to the Windows Event Log if supported."""

    if platform.system() != "Windows" or ctypes is None:
        return
    try:
        advapi = ctypes.windll.advapi32  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - defensive
        return
    event_type = _EVENT_TYPES.get(level.upper(), _EVENT_TYPES["INFO"])
    handle = advapi.RegisterEventSourceW(None, wintypes.LPCWSTR(source))  # type: ignore[arg-type]
    if not handle:  # pragma: no cover - failure is logged silently
        _LOGGER.debug("Failed to register event source %s", source)
        return
    try:
        strings = (wintypes.LPCWSTR * 1)(message)
        advapi.ReportEventW(
            handle,
            event_type,
            0,
            1,
            None,
            1,
            0,
            ctypes.cast(strings, ctypes.POINTER(wintypes.LPCWSTR)),
            None,
        )
    except Exception:  # pragma: no cover - best effort
        _LOGGER.debug("ReportEventW failed", exc_info=True)
    finally:
        try:
            advapi.DeregisterEventSource(handle)
        except Exception:  # pragma: no cover - best effort
            _LOGGER.debug("Failed to deregister event source", exc_info=True)


__all__ = ["write_event_log"]
