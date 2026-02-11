from __future__ import annotations

import pytest

from earCrawler.rag import pipeline


def test_pipeline_refuses_when_retrieval_thin(monkeypatch) -> None:
    monkeypatch.setenv("EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL", "1")
    monkeypatch.setenv("EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE", "0.5")
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    monkeypatch.setenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "1")

    monkeypatch.setattr(
        pipeline,
        "retrieve_regulation_context",
        lambda *_a, **_k: [
            {
                "section_id": "EAR-736.2(b)",
                "text": "General prohibitions apply to covered exports unless authorized.",
                "score": 0.3,
                "raw": {},
            }
        ],
    )
    monkeypatch.setattr(pipeline, "expand_with_kg", lambda *_a, **_k: [])

    def _fail_if_called(*_a, **_k):
        raise AssertionError("generate_chat must not be called when refusing on thin retrieval")

    monkeypatch.setattr(pipeline, "generate_chat", _fail_if_called)

    result = pipeline.answer_with_rag(
        "Can you decide this from the excerpt?",
        strict_retrieval=False,
        strict_output=True,
    )

    assert result["output_ok"] is True
    assert result["label"] == "unanswerable"
    assert "Insufficient" in (result["answer"] or "")
    assert "Need" in (result["answer"] or "")
    assert result["citations"] == []
    assert result["llm_enabled"] is False
    assert result["disabled_reason"] == "insufficient_evidence"
