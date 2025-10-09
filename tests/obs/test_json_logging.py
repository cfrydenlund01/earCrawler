from __future__ import annotations

import io
import json
import logging

from earCrawler.utils.log_json import JsonLogger


def _make_logger(*, max_details: int = 256) -> tuple[JsonLogger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger("earcrawler.test.json")
    logger.handlers = []
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    json_logger = JsonLogger("api", logger=logger, eventlog_enabled=False, max_details_bytes=max_details, sample_rate=1.0)
    return json_logger, stream


def test_json_logger_emits_required_fields():
    logger, stream = _make_logger()
    logger.emit(
        "INFO",
        "request",
        trace_id="abc123",
        route="/v1/test",
        latency_ms=12.5,
        status=200,
        details={"token": "tokensecretABCDEFGHIJKLMNOPQRST", "email": "user@example.com"},
    )
    payload = json.loads(stream.getvalue())
    assert payload["event"] == "request"
    assert payload["trace_id"] == "abc123"
    assert payload["route"] == "/v1/test"
    assert payload["latency_ms"] == 12.5
    assert payload["status"] == 200
    assert payload["details"]["token"] == "[redacted]"
    assert payload["details"]["email"] == "[redacted]"


def test_json_logger_truncates_large_details():
    logger, stream = _make_logger(max_details=32)
    large = {"values": list(range(100))}
    logger.emit("INFO", "large", details=large)
    payload = json.loads(stream.getvalue())
    assert payload["event"] == "large"
    assert "preview" in payload["details"]
