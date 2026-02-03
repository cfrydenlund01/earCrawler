from __future__ import annotations

import pytest

from earCrawler.rag import pipeline


def _stub_retrieval(*_args, **_kwargs):
    return []


def _stub_expansion(*_args, **_kwargs):
    return []


@pytest.fixture(autouse=True)
def _stub_retrieval_and_kg(monkeypatch):
    monkeypatch.setattr(pipeline, "retrieve_regulation_context", _stub_retrieval)
    monkeypatch.setattr(pipeline, "expand_with_kg", _stub_expansion)
    yield


def test_pipeline_marks_freeform_output_invalid(monkeypatch):
    monkeypatch.setattr(pipeline, "generate_chat", lambda *a, **k: "plain text response")

    result = pipeline.answer_with_rag(
        "What is required?",
        retriever=None,
        strict_retrieval=False,
        strict_output=True,
    )

    assert result["output_ok"] is False
    assert result["output_error"]["code"] == "invalid_json"
    assert result["answer"] is None
    assert result["label"] is None


def test_pipeline_rejects_extra_keys(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "generate_chat",
        lambda *a, **k: (
            '{'
            '"label":"permitted",'
            '"answer_text":"Yes",'
            '"citations":[],'
            '"evidence_okay":{"ok":true,"reasons":[]},'
            '"assumptions":[],'
            '"extra":1'
            '}'
        ),
    )

    result = pipeline.answer_with_rag(
        "Question?",
        strict_retrieval=False,
        strict_output=True,
    )

    assert result["output_ok"] is False
    assert result["output_error"]["code"] == "extra_key"
    assert result["answer"] is None


def test_pipeline_accepts_valid_json(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "retrieve_regulation_context",
        lambda *a, **k: [{"section_id": "EAR-740.1", "text": "License Exceptions intro", "score": 1.0, "raw": {}}],
    )
    monkeypatch.setattr(
        pipeline,
        "generate_chat",
        lambda *a, **k: (
            '{'
            '"label":"permitted",'
            '"answer_text":"Yes",'
            '"citations":[{"section_id":"EAR-740.1","quote":"License Exceptions intro","span_id":""}],'
            '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
            '"assumptions":[]'
            '}'
        ),
    )

    result = pipeline.answer_with_rag(
        "Question?",
        strict_retrieval=False,
        strict_output=True,
    )

    assert result["output_ok"] is True
    assert result["answer"] == "Yes"
    assert result["label"] == "permitted"
    assert result["citations"][0]["quote"] == "License Exceptions intro"


def test_pipeline_rejects_ungrounded_quote(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "retrieve_regulation_context",
        lambda *a, **k: [{"section_id": "EAR-740.1", "text": "License Exceptions intro", "score": 1.0, "raw": {}}],
    )
    monkeypatch.setattr(
        pipeline,
        "generate_chat",
        lambda *a, **k: (
            '{'
            '"label":"permitted",'
            '"answer_text":"Yes",'
            '"citations":[{"section_id":"EAR-740.1","quote":"NOT IN CONTEXT","span_id":""}],'
            '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
            '"assumptions":[]'
            '}'
        ),
    )

    result = pipeline.answer_with_rag(
        "Question?",
        strict_retrieval=False,
        strict_output=True,
    )

    assert result["output_ok"] is False
    assert result["output_error"]["code"] == "ungrounded_citation"
    assert result["answer"] is None
