from __future__ import annotations

from pathlib import Path

import requests
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from earCrawler.utils.http_cache import HTTPCache


class DummySession:
    def __init__(self, response: requests.Response):
        self._response = response

    def get(self, url, params, headers, timeout):  # pragma: no cover - simple pass-through
        return self._response


def make_response(text: str | None, content_type: str) -> requests.Response:
    resp = requests.Response()
    resp.status_code = 200
    resp._content = (text or "").encode("utf-8")
    resp.headers["Content-Type"] = content_type
    return resp


def test_skip_cache_for_non_json(tmp_path: Path) -> None:
    cache = HTTPCache(tmp_path)
    resp = make_response("not json", "text/html")
    session = DummySession(resp)
    cache.get(session, "https://example.com", {})
    assert not list(tmp_path.iterdir())


def test_cache_written_for_json(tmp_path: Path) -> None:
    cache = HTTPCache(tmp_path)
    resp = make_response("{\"a\":1}", "application/json; charset=utf-8")
    session = DummySession(resp)
    cache.get(session, "https://example.com", {})
    assert any(tmp_path.iterdir())
