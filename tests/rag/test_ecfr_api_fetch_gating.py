from __future__ import annotations

from pathlib import Path

import pytest

from earCrawler.rag.ecfr_api_fetch import fetch_ecfr_snapshot


def test_fetch_requires_network_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EARCRAWLER_ALLOW_NETWORK", raising=False)
    with pytest.raises(RuntimeError):
        fetch_ecfr_snapshot(tmp_path / "out.jsonl")


def test_fetch_raises_when_upstream_returns_non_200(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EARCRAWLER_ALLOW_NETWORK", "1")

    class _Resp:
        status_code = 503
        text = "<html>down</html>"

    class _Session:
        headers = {}

        def get(self, url: str, timeout: int = 60):
            return _Resp()

    monkeypatch.setattr("earCrawler.rag.ecfr_api_fetch.requests.Session", _Session)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        fetch_ecfr_snapshot(tmp_path / "out.jsonl", title="15", date="current", parts=["740"])


def test_fetch_raises_when_upstream_payload_has_no_sections(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EARCRAWLER_ALLOW_NETWORK", "1")

    class _Resp:
        status_code = 200
        text = "<html><body><div>No section nodes</div></body></html>"

    class _Session:
        headers = {}

        def get(self, url: str, timeout: int = 60):
            return _Resp()

    monkeypatch.setattr("earCrawler.rag.ecfr_api_fetch.requests.Session", _Session)
    with pytest.raises(RuntimeError, match="No sections parsed"):
        fetch_ecfr_snapshot(tmp_path / "out.jsonl", title="15", date="current", parts=["740"])
