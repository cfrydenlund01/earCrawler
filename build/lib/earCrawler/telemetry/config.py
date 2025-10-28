from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

CONFIG_ENV = "EAR_TELEMETRY_CONFIG"


def _default_base() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "EarCrawler"
    # Fallback for non-Windows platforms
    return Path.home() / ".earcrawler"


def config_path() -> Path:
    env = os.getenv(CONFIG_ENV)
    if env:
        return Path(env)
    base = _default_base()
    base.mkdir(parents=True, exist_ok=True)
    return base / "telemetry.json"


def _default_spool_dir() -> str:
    if os.getenv("EAR_SYSTEM_INSTALL") == "1":
        base = os.getenv("PROGRAMDATA") or os.getenv("APPDATA") or str(Path.home())
    else:
        base = os.getenv("APPDATA") or str(Path.home())
    return str(Path(base) / "EarCrawler" / "spool")


@dataclass
class TelemetryConfig:
    enabled: bool = False
    sample_rate: float = 1.0
    endpoint: str | None = None
    spool_dir: str = _default_spool_dir()
    max_spool_mb: int = 256
    max_file_mb: int = 8
    max_age_days: int = 30
    keep_last_n: int = 10
    device_id: str = uuid.uuid4().hex
    auth_secret_name: str | None = None


def load_config() -> TelemetryConfig:
    path = config_path()
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        return TelemetryConfig(**data)
    return TelemetryConfig()


def save_config(cfg: TelemetryConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, indent=2)
