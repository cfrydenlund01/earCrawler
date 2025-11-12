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
from typing import Any, Dict, Iterable

from earCrawler.telemetry import redaction
from earCrawler.security import cred_store

__all__ = ["append_event", "verify_chain", "rotate", "tail", "current_log_path"]


def _base_dir() -> Path:
    override = os.getenv("EARCTL_AUDIT_DIR")
    if override:
        return Path(override)
    prog = os.getenv("PROGRAMDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(prog) / "EarCrawler" / "audit"


def current_log_path() -> Path:
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


def append_event(
    event: str,
    user: str,
    roles: Iterable[str],
    command: str,
    args_sanitized: str,
    exit_code: int,
    duration_ms: int,
) -> None:
    path = current_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
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
    prev = _prev_hash(path)
    entry["chain_prev"] = prev
    sanitized = dict(entry)
    sanitized["args_sanitized"] = redaction.redact(entry.get("args_sanitized", ""))
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


def rotate() -> Path:
    path = current_log_path()
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        new_path = path.with_name(f"{path.stem}-{ts}{path.suffix}")
        path.rename(new_path)
        return new_path
    return path


def tail(n: int = 50) -> Iterable[dict]:
    path = current_log_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()[-n:]
    return [json.loads(line) for line in lines]


def verify_chain(path: Path) -> bool:
    prev = "0" * 64
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            entry = json.loads(line)
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
            if entry.get("chain_prev") != prev or entry.get("chain_hash") != expected:
                return False
            hmac_key = cred_store.get_secret("EARCTL_AUDIT_HMAC_KEY")
            if (
                hmac_key
                and entry.get("hmac")
                != hmaclib.new(
                    hmac_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
                ).hexdigest()
            ):
                return False
            prev = entry["chain_hash"]
    return True
