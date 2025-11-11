from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Iterable

import requests

from .config import TelemetryConfig


class HTTPSink:
    """Send telemetry events to a remote endpoint with backoff (sync)."""

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


# Optional async sink for use in event-loop contexts
try:  # pragma: no cover - httpx may not be installed in minimal envs
    import httpx
except Exception:  # pragma: no cover
    httpx = None


class AsyncHTTPSink:
    """Async telemetry sender with connection pooling and async backoff."""

    def __init__(self, cfg: TelemetryConfig):
        if httpx is None:  # type: ignore[name-defined]
            raise RuntimeError("AsyncHTTPSink requires httpx; install optional dependency to enable HTTP sink")
        self.cfg = cfg
        self.backoff = 1.0
        self._client: httpx.AsyncClient | None = None  # type: ignore[name-defined]

    async def _ensure_client(self) -> "httpx.AsyncClient":  # type: ignore[name-defined]
        if httpx is None:
            raise RuntimeError("httpx not available for AsyncHTTPSink")
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None

    async def send(self, events: Iterable[dict]) -> None:
        if not self.cfg.endpoint:
            return
        if HTTPSink._disabled():
            return
        data = "\n".join(json.dumps(e) for e in events)
        for _ in range(5):
            try:
                client = await self._ensure_client()
                resp = await client.post(self.cfg.endpoint, content=data, timeout=5.0)
                resp.raise_for_status()
                self.backoff = 1.0
                return
            except Exception:
                # Non-blocking backoff
                await asyncio.sleep(self.backoff + random.random())
                self.backoff = min(self.backoff * 2.0, 60.0)


__all__ = ["HTTPSink", "AsyncHTTPSink"]
