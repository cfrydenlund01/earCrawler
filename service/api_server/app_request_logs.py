from __future__ import annotations

"""Async request-log sink wiring for API startup."""

import asyncio

from fastapi import FastAPI

from earCrawler.observability.config import ObservabilityConfig
from earCrawler.telemetry.config import TelemetryConfig
from earCrawler.telemetry.sink_http import AsyncHTTPSink
from earCrawler.utils.log_json import JsonLogger


def configure_request_log_sink(
    app: FastAPI, *, observability: ObservabilityConfig, json_logger: JsonLogger
) -> None:
    """Attach optional async HTTP sink for structured request logs."""

    app.state.request_log_queue = None
    app.state.request_log_task = None

    http_sink_cfg = observability.request_http_sink
    if not (http_sink_cfg.enabled and http_sink_cfg.endpoint):
        return

    try:
        sink = AsyncHTTPSink(
            TelemetryConfig(enabled=True, endpoint=http_sink_cfg.endpoint)
        )
    except RuntimeError as exc:
        json_logger.warning("telemetry.http_sink.disabled", reason=str(exc))
        return

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(
        maxsize=http_sink_cfg.queue_max
    )
    flush_interval = max(0.1, http_sink_cfg.flush_ms / 1000.0)
    batch_size = max(1, http_sink_cfg.batch_size)

    async def _drain_request_logs() -> None:
        batch: list[dict[str, object]] = []
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=flush_interval)
                    batch.append(item)
                    if len(batch) >= batch_size:
                        await sink.send(list(batch))
                        batch.clear()
                except asyncio.TimeoutError:
                    if batch:
                        await sink.send(list(batch))
                        batch.clear()
        except asyncio.CancelledError:
            while True:
                if batch:
                    await sink.send(list(batch))
                    batch.clear()
                try:
                    batch.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            raise
        finally:
            if batch:
                await sink.send(list(batch))
            await sink.aclose()

    async def _start_request_logs() -> None:
        app.state.request_log_task = asyncio.create_task(_drain_request_logs())

    async def _stop_request_logs() -> None:
        task = getattr(app.state, "request_log_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            app.state.request_log_task = None
        else:
            await sink.aclose()

    app.state.request_log_queue = queue
    app.add_event_handler("startup", _start_request_logs)
    app.add_event_handler("shutdown", _stop_request_logs)
