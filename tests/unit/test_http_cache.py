from __future__ import annotations

from pathlib import Path

import requests
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from earCrawler.utils.http_cache import HTTPCache


class DummySession:
    def __init__(self, response: requests.Response):
        self._response = response

    def get(
        self, url, params, headers, timeout
    ):  # pragma: no cover - simple pass-through
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
    resp = make_response('{"a":1}', "application/json; charset=utf-8")
    session = DummySession(resp)
    cache.get(session, "https://example.com", {})
    assert any(tmp_path.iterdir())


def test_cache_sets_flag_and_reuses_response(tmp_path: Path) -> None:
    cache = HTTPCache(tmp_path)
    first = make_response('{"a":1}', "application/json")
    session = DummySession(first)
    result1 = cache.get(session, "https://example.com", {})
    assert not getattr(result1, "from_cache", False)

    session._response = make_response('{"a":1}', "application/json")
    result2 = cache.get(session, "https://example.com", {})
    assert getattr(result2, "from_cache", False)


def test_vary_headers_affects_cache_key(tmp_path: Path) -> None:
    cache = HTTPCache(tmp_path)
    session = DummySession(make_response('{"a":1}', "application/json"))
    cache.get(
        session,
        "https://example.com",
        {},
        headers={"Accept": "application/json"},
        vary_headers=("Accept",),
    )
    initial_files = list(tmp_path.glob("*.json"))
    assert len(initial_files) == 1

    session._response = make_response('{"a":1}', "application/json")
    cache.get(
        session,
        "https://example.com",
        {},
        headers={"Accept": "text/plain"},
        vary_headers=("Accept",),
    )
    new_files = list(tmp_path.glob("*.json"))
    assert len(new_files) == 2
