from __future__ import annotations

import requests
import pytest

from api_clients.ori_client import ORIClient, ORIClientError


class _AlwaysFailSession:
    def get(self, url: str, timeout: int = 10):  # pragma: no cover - stub
        raise requests.ConnectionError("offline")

    def close(self):  # pragma: no cover - stub
        return None


class _EmptyBodyResponse:
    status_code = 200
    text = "  "

    def raise_for_status(self):
        return None


class _EmptyBodySession:
    def get(self, url: str, timeout: int = 10):  # pragma: no cover - stub
        return _EmptyBodyResponse()

    def close(self):  # pragma: no cover - stub
        return None


class _HttpErrorResponse:
    status_code = 404
    text = "not found"

    def raise_for_status(self):
        err = requests.HTTPError("404")
        err.response = self
        raise err


class _HttpErrorSession:
    def get(self, url: str, timeout: int = 10):  # pragma: no cover - stub
        return _HttpErrorResponse()

    def close(self):  # pragma: no cover - stub
        return None


def test_get_listing_html_retry_exhausted_sets_status(monkeypatch):
    monkeypatch.setattr("api_clients.ori_client.time.sleep", lambda *_: None)
    client = ORIClient(session=_AlwaysFailSession())
    with pytest.raises(ORIClientError) as exc:
        client.get_listing_html()
    assert exc.value.state == "retry_exhausted"
    status = client.get_last_status("get_listing_html")
    assert status is not None
    assert status.state == "retry_exhausted"


def test_get_case_html_invalid_response_sets_status():
    client = ORIClient(session=_EmptyBodySession())
    with pytest.raises(ORIClientError) as exc:
        client.get_case_html("https://ori.hhs.gov/case/ABC")
    assert exc.value.state == "invalid_response"
    status = client.get_last_status("get_case_html")
    assert status is not None
    assert status.state == "invalid_response"


def test_get_listing_html_http_404_sets_upstream_unavailable() -> None:
    client = ORIClient(session=_HttpErrorSession())
    with pytest.raises(ORIClientError) as exc:
        client.get_listing_html()
    assert exc.value.state == "upstream_unavailable"
    assert exc.value.status_code == 404
    status = client.get_last_status("get_listing_html")
    assert status is not None
    assert status.state == "upstream_unavailable"


def test_get_listing_html_result_returns_typed_failure(monkeypatch):
    monkeypatch.setattr("api_clients.ori_client.time.sleep", lambda *_: None)
    client = ORIClient(session=_AlwaysFailSession())
    result = client.get_listing_html_result()
    assert result.data == ""
    assert result.state == "retry_exhausted"


def test_get_case_html_result_returns_typed_failure() -> None:
    client = ORIClient(session=_EmptyBodySession())
    result = client.get_case_html_result("https://ori.hhs.gov/case/ABC")
    assert result.data == ""
    assert result.state == "invalid_response"
