from __future__ import annotations

import sys
import threading

import pytest

from service.api_server.config import RateLimitConfig
from service.api_server.limits import RateLimiter

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


def test_rate_limiter_thread_safe_under_concurrency(monkeypatch) -> None:
    monkeypatch.setattr("service.api_server.limits.time.monotonic", lambda: 1000.0)
    config = RateLimitConfig(
        anonymous_per_minute=1,
        authenticated_per_minute=1,
        anonymous_burst=1,
        authenticated_burst=1,
    )
    workers = 16
    rounds = 40
    original_switch = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for idx in range(rounds):
            limiter = RateLimiter(config)
            start = threading.Barrier(workers)
            lock = threading.Lock()
            allowed = 0

            def worker() -> None:
                nonlocal allowed
                start.wait()
                _, retry_after, _ = limiter.check(
                    identity="ip:127.0.0.1",
                    scope=f"/v1/search/{idx}",
                    authenticated=False,
                )
                if retry_after == 0.0:
                    with lock:
                        allowed += 1

            threads = [threading.Thread(target=worker) for _ in range(workers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            assert allowed == 1
    finally:
        sys.setswitchinterval(original_switch)
