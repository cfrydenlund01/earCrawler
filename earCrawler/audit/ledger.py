from __future__ import annotations

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import hmac as hmaclib
import subprocess
import sys
from typing import Any, Dict, Iterable, Mapping

from earCrawler.telemetry import redaction
from earCrawler.security import cred_store

__all__ = [
    "append_event",
    "append_fact",
    "verify_chain",
    "verify_chain_report",
    "rotate",
    "tail",
    "current_log_path",
]


def _base_dir() -> Path:
    override = os.getenv("EARCTL_AUDIT_DIR")
    if override:
        return Path(override)
    prog = os.getenv("PROGRAMDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(prog) / "EarCrawler" / "audit"


def _safe_run_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value)
    return safe.strip("-.")


def current_log_path(run_id: str | None = None) -> Path:
    run_ref = str(run_id or os.getenv("EARCTL_AUDIT_RUN_ID") or "").strip()
    if run_ref:
        safe_run = _safe_run_id(run_ref)
        if safe_run:
            return _base_dir() / "runs" / f"{safe_run}.jsonl"
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _base_dir() / f"{day}.jsonl"


def _prev_hash(path: Path) -> str:
    if not path.exists():
        return "0" * 64
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            if size == 0:
                return "0" * 64
            off = min(1024, size)
            fh.seek(-off, os.SEEK_END)
            lines = fh.readlines()[-1:]
            if not lines:
                return "0" * 64
            last = json.loads(lines[0])
            return last.get("chain_hash", "0" * 64)
    except Exception:
        return "0" * 64


def _commit_hash() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        return out
    except Exception:
        return "unknown"


def _append_entry(entry: Mapping[str, Any], *, redact_args: bool, run_id: str | None = None) -> None:
    path = current_log_path(run_id=run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = _prev_hash(path)
    sanitized = dict(entry)
    if redact_args:
        sanitized["args_sanitized"] = redaction.redact(str(entry.get("args_sanitized", "")))
    sanitized["chain_prev"] = prev
    base = {
        k: sanitized[k]
        for k in sanitized
        if k not in {"chain_prev", "chain_hash", "hmac"}
    }
    canonical = json.dumps(base, sort_keys=True, separators=(",", ":"))
    sanitized["chain_hash"] = hashlib.sha256(
        (prev + canonical).encode("utf-8")
    ).hexdigest()
    hmac_key = cred_store.get_secret("EARCTL_AUDIT_HMAC_KEY")
    if hmac_key:
        sanitized["hmac"] = hmaclib.new(
            hmac_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(sanitized, ensure_ascii=False) + "\n")
    except Exception:
        print("audit log write failed", file=sys.stderr)


def append_event(
    event: str,
    user: str,
    roles: Iterable[str],
    command: str,
    args_sanitized: str,
    exit_code: int,
    duration_ms: int,
    run_id: str | None = None,
) -> None:
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user": user,
        "roles": list(roles),
        "command": command,
        "args_sanitized": args_sanitized,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "host": platform.node(),
        "commit": _commit_hash(),
    }
    _append_entry(entry, redact_args=True, run_id=run_id)


def append_fact(event: str, payload: Mapping[str, Any], run_id: str | None = None) -> None:
    """Append a structured non-command fact to the audit ledger."""

    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "host": platform.node(),
        "commit": _commit_hash(),
        "payload": dict(payload),
    }
    _append_entry(entry, redact_args=False, run_id=run_id)


def rotate() -> Path:
    path = current_log_path()
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        new_path = path.with_name(f"{path.stem}-{ts}{path.suffix}")
        path.rename(new_path)
        return new_path
    return path


def tail(n: int = 50, run_id: str | None = None) -> Iterable[dict]:
    path = current_log_path(run_id=run_id)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()[-n:]
    return [json.loads(line) for line in lines]


def verify_chain_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "ok": False,
            "path": str(path),
            "checked_entries": 0,
            "line": 0,
            "reason": "missing_file",
        }

    prev = "0" * 64
    checked_entries = 0
    hmac_key = cred_store.get_secret("EARCTL_AUDIT_HMAC_KEY")
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            checked_entries = line_no
            try:
                entry = json.loads(line)
            except Exception:
                return {
                    "ok": False,
                    "path": str(path),
                    "checked_entries": line_no - 1,
                    "line": line_no,
                    "reason": "invalid_json",
                }
            canonical = json.dumps(
                {
                    k: entry[k]
                    for k in entry
                    if k not in {"chain_prev", "chain_hash", "hmac"}
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            expected = hashlib.sha256((prev + canonical).encode("utf-8")).hexdigest()
            if entry.get("chain_prev") != prev:
                return {
                    "ok": False,
                    "path": str(path),
                    "checked_entries": line_no - 1,
                    "line": line_no,
                    "reason": "chain_prev_mismatch",
                    "expected_chain_prev": prev,
                    "actual_chain_prev": entry.get("chain_prev"),
                    "event": entry.get("event"),
                }
            if entry.get("chain_hash") != expected:
                return {
                    "ok": False,
                    "path": str(path),
                    "checked_entries": line_no - 1,
                    "line": line_no,
                    "reason": "chain_hash_mismatch",
                    "expected_chain_hash": expected,
                    "actual_chain_hash": entry.get("chain_hash"),
                    "event": entry.get("event"),
                }
            if hmac_key:
                expected_hmac = hmaclib.new(
                    hmac_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
                ).hexdigest()
                if entry.get("hmac") != expected_hmac:
                    return {
                        "ok": False,
                        "path": str(path),
                        "checked_entries": line_no - 1,
                        "line": line_no,
                        "reason": "hmac_mismatch",
                        "event": entry.get("event"),
                    }
            prev = entry["chain_hash"]
    return {
        "ok": True,
        "path": str(path),
        "checked_entries": checked_entries,
        "line": None,
        "reason": None,
    }


def verify_chain(path: Path) -> bool:
    return bool(verify_chain_report(path).get("ok"))
