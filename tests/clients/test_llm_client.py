from __future__ import annotations

import os

import pytest
import requests

from api_clients.llm_client import LLMProviderError, generate_chat


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    # Ensure remote LLM calls are allowed for these isolated tests.
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    # Keep unit tests deterministic even when a developer has a local secrets file.
    monkeypatch.setenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "1")
    # Clear provider-specific budgets to avoid surprises.
    for key in (
        "LLM_MAX_CALLS",
        "LLM_OPENROUTER_MAX_CALLS",
        "LLM_NVIDIA_NIM_MAX_CALLS",
        "LLM_GROQ_MAX_CALLS",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    # Cleanup of env happens automatically via monkeypatch


def test_generate_chat_missing_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMProviderError):
        generate_chat([{"role": "user", "content": "ping"}])


def test_generate_chat_success(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "dummy")
    # Ensure we don't hit the network.
    def fake_post(self, url, headers=None, json=None, timeout=None):
        class Resp:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "pong"}}]}

            text = ""

        fake_post.called = True
        return Resp()

    fake_post.called = False
    monkeypatch.setattr(requests.Session, "post", fake_post, raising=True)

    result = generate_chat([{"role": "user", "content": "ping"}])
    assert result == "pong"
    assert fake_post.called


def test_generate_chat_retries_on_429(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "dummy")
    monkeypatch.setenv("LLM_RETRY_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("LLM_RETRY_BASE_SECONDS", "0.0")
    monkeypatch.setenv("LLM_RETRY_MAX_SECONDS", "0.0")
    monkeypatch.setenv("LLM_RETRY_JITTER_SECONDS", "0.0")

    calls = {"count": 0}

    class Resp429:
        status_code = 429
        headers = {"Retry-After": "0"}
        text = "rate limited"

        def json(self):
            return {
                "error": {
                    "message": "Rate limit reached. Please try again in 0s."
                }
            }

    class Resp200:
        status_code = 200
        headers = {}
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "pong"}}]}

    def fake_post(self, url, headers=None, json=None, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return Resp429()
        return Resp200()

    sleeps: list[float] = []

    import api_clients.llm_client as llm_client

    monkeypatch.setattr(requests.Session, "post", fake_post, raising=True)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: sleeps.append(s), raising=True)

    result = generate_chat([{"role": "user", "content": "ping"}])
    assert result == "pong"
    assert calls["count"] == 2
    assert len(sleeps) == 1


def test_generate_chat_throttles_between_calls(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "dummy")
    monkeypatch.setenv("LLM_MIN_INTERVAL_SECONDS", "10.0")
    monkeypatch.setenv("LLM_RETRY_MAX_ATTEMPTS", "1")

    class Resp200:
        status_code = 200
        headers = {}
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "pong"}}]}

    def fake_post(self, url, headers=None, json=None, timeout=None):
        return Resp200()

    import api_clients.llm_client as llm_client

    # Simulate a second call occurring shortly after the first.
    t = {"now": 0.0}

    def fake_monotonic():
        return t["now"]

    sleeps: list[float] = []

    def fake_sleep(seconds: float):
        sleeps.append(seconds)
        t["now"] += seconds

    monkeypatch.setattr(requests.Session, "post", fake_post, raising=True)
    monkeypatch.setattr(llm_client.time, "monotonic", fake_monotonic, raising=True)
    monkeypatch.setattr(llm_client.time, "sleep", fake_sleep, raising=True)

    # First call at t=0 (no throttle expected).
    assert generate_chat([{"role": "user", "content": "ping"}]) == "pong"
    # Advance time a bit, but not enough to satisfy the min interval.
    t["now"] += 2.0
    # Second call should sleep for ~8s to reach 10s since last request.
    assert generate_chat([{"role": "user", "content": "ping"}]) == "pong"
    assert sleeps and sleeps[-1] == pytest.approx(8.0, abs=1e-6)
