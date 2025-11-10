from __future__ import annotations

import json
import random
import time
from typing import Iterable

import requests

from .config import TelemetryConfig


class HTTPSink:
    """Send telemetry events to a remote endpoint with backoff."""

    def __init__(self, cfg: TelemetryConfig):
        self.cfg = cfg
        self.backoff = 1

    def send(self, events: Iterable[dict]) -> None:
        if not self.cfg.endpoint:
            return
        if self._disabled():
            return
        data = "\n".join(json.dumps(e) for e in events)
        for _ in range(5):
            try:
                resp = requests.post(self.cfg.endpoint, data=data, timeout=5)
                resp.raise_for_status()
                self.backoff = 1
                return
            except Exception:
                time.sleep(self.backoff + random.random())
                self.backoff = min(self.backoff * 2, 60)

    @staticmethod
    def _disabled() -> bool:
        return bool(int(__import__("os").getenv("EAR_NO_TELEM_HTTP", "0")))
