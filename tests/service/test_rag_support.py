from __future__ import annotations

from pathlib import Path
import time

import pytest

from service.api_server import rag_support


class _CaptureLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, **fields) -> None:
        self.events.append(("info", event, dict(fields)))

    def warning(self, event: str, **fields) -> None:
        self.events.append(("warning", event, dict(fields)))


def _has_event(
    events: list[tuple[str, str, dict[str, object]]],
    level: str,
    event: str,
    *,
    reason: str | None = None,
) -> bool:
    for seen_level, seen_event, fields in events:
        if seen_level != level or seen_event != event:
            continue
        if reason is None or fields.get("reason") == reason:
            return True
    return False


def test_load_retriever_returns_null_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EARCRAWLER_API_ENABLE_RAG", "0")
    retriever = rag_support.load_retriever()
    assert isinstance(retriever, rag_support.NullRetriever)
    assert retriever.failure_type == "retriever_disabled"


def test_load_retriever_returns_broken_for_index_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EARCRAWLER_API_ENABLE_RAG", "1")
    monkeypatch.setenv("EARCRAWLER_FAISS_INDEX", str(Path("missing/index.faiss")))
    import earCrawler.rag.retriever as retriever_mod

    original = retriever_mod.Retriever

    def _raise_index_missing(*args, **kwargs):
        raise retriever_mod.IndexMissingError(Path("missing/index.faiss"))

    monkeypatch.setattr(retriever_mod, "Retriever", _raise_index_missing)
    try:
        retriever = rag_support.load_retriever()
    finally:
        monkeypatch.setattr(retriever_mod, "Retriever", original)

    assert isinstance(retriever, rag_support.BrokenRetriever)
    assert retriever.failure_type == "index_missing"


def test_warmup_skips_for_disabled_and_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EARCRAWLER_WARM_RETRIEVER", "1")
    monkeypatch.setenv("EARCRAWLER_WARM_RETRIEVER_TIMEOUT_SECONDS", "1")
    capture = _CaptureLogger()

    outcome = rag_support.warm_retriever_if_enabled(
        rag_support.NullRetriever(),
        request_logger=capture,  # type: ignore[arg-type]
    )
    assert outcome.status == "skipped"
    assert outcome.reason == "retriever_disabled"
    assert _has_event(
        capture.events, "info", "rag.warmup.skipped", reason="retriever_disabled"
    )

    broken = rag_support.BrokenRetriever(
        RuntimeError("broken"),
        failure_type="retriever_init_failed",
    )
    outcome = rag_support.warm_retriever_if_enabled(
        broken,
        request_logger=capture,  # type: ignore[arg-type]
    )
    assert outcome.status == "skipped"
    assert outcome.reason == "retriever_init_fai"
    assert _has_event(
        capture.events,
        "info",
        "rag.warmup.skipped",
        reason="retriever_init_fai",
    )


def test_warmup_timeout_logs_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EARCRAWLER_WARM_RETRIEVER", "1")
    monkeypatch.setenv("EARCRAWLER_WARM_RETRIEVER_TIMEOUT_SECONDS", "0.01")
    capture = _CaptureLogger()

    class _SlowRetriever:
        enabled = True
        ready = True

        def warm(self) -> None:
            time.sleep(0.1)

    outcome = rag_support.warm_retriever_if_enabled(
        _SlowRetriever(),
        request_logger=capture,  # type: ignore[arg-type]
    )
    assert outcome.status == "timeout"
    assert outcome.reason == "timeout"
    assert _has_event(capture.events, "warning", "rag.warmup.skipped", reason="timeout")
