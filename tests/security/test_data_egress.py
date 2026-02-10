from __future__ import annotations

from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.security.data_egress import (
    build_data_egress_decision,
    hash_messages,
    hash_text,
)


def test_hash_text_normalizes_newlines_and_trailing_whitespace() -> None:
    assert hash_text("line 1  \r\nline 2\t\r\n") == hash_text("line 1\nline 2")


def test_hash_messages_is_stable_for_equivalent_payloads() -> None:
    left = [{"role": "user", "content": "hello  \r\nworld"}]
    right = [{"content": "hello\nworld", "role": "user"}]
    assert hash_messages(left) == hash_messages(right)


def test_decision_record_is_hash_only() -> None:
    contexts = ["[EAR-734.3] Example EAR passage text about exports."]
    decision = build_data_egress_decision(
        remote_enabled=True,
        disabled_reason=None,
        provider="groq",
        model="llama-3.3-70b-versatile",
        redaction_mode="none",
        question="Can we export this item?",
        contexts=contexts,
        messages=[{"role": "user", "content": "Context and question payload"}],
        trace_id="trace-1",
    ).to_dict()
    as_text = str(decision)
    assert "Can we export this item?" not in as_text
    assert "Example EAR passage text about exports." not in as_text
    assert len(decision["prompt_hash"]) == 64
    assert len(decision["question_hash"]) == 64
    assert decision["context_count"] == 1
    assert all(len(h) == 64 for h in decision["context_hashes"])


def test_remote_policy_default_deny(monkeypatch) -> None:
    monkeypatch.setenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "1")
    monkeypatch.delenv("EARCRAWLER_REMOTE_LLM_POLICY", raising=False)
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    denied_cfg = get_llm_config()
    assert denied_cfg.enable_remote is False
    assert denied_cfg.remote_policy == "deny"

    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    allowed_cfg = get_llm_config()
    assert allowed_cfg.enable_remote is True
    assert allowed_cfg.remote_policy == "allow"
