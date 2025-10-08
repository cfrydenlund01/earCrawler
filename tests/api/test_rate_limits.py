from __future__ import annotations

import pytest

pytestmark = pytest.mark.enable_socket


def test_rate_limit_exceeded(app) -> None:
    for _ in range(5):
        res = app.get("/v1/search", params={"q": "export"})
        assert res.status_code == 200
    res = app.get("/v1/search", params={"q": "export"})
    assert res.status_code == 429
    payload = res.json()
    assert payload["status"] == 429
    assert "Retry-After" in res.headers
    assert res.headers["X-RateLimit-Limit"]
    assert res.headers["X-RateLimit-Remaining"] == "0"
