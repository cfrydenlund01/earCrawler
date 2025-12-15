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
