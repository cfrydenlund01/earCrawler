from __future__ import annotations

from earCrawler.rag import pipeline


class _StubRetriever:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = list(docs)
        self.calls: list[tuple[str, int]] = []

    def query(self, prompt: str, k: int = 5) -> list[dict]:
        self.calls.append((prompt, k))
        return list(self.docs)


def _doc(
    *,
    section: str,
    text: str,
    score: float,
    snapshot_date: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
) -> dict:
    payload = {
        "doc_id": section,
        "section_id": section,
        "section": section,
        "text": text,
        "score": score,
        "source_ref": "snapshot-test",
    }
    if snapshot_date:
        payload["snapshot_date"] = snapshot_date
    if effective_from:
        payload["effective_from"] = effective_from
    if effective_to:
        payload["effective_to"] = effective_to
    return payload


def test_retrieve_regulation_context_selects_applicable_snapshot() -> None:
    retriever = _StubRetriever(
        [
            _doc(
                section="EAR-740.1",
                text="Version current in 2025.",
                score=0.95,
                snapshot_date="2025-01-01",
            ),
            _doc(
                section="EAR-740.1",
                text="Version current in 2024.",
                score=0.90,
                snapshot_date="2024-01-01",
            ),
        ]
    )
    temporal_state: dict[str, object] = {}

    results = pipeline.retrieve_regulation_context(
        "What rule applied as of 2024-06-01?",
        top_k=1,
        retriever=retriever,
        temporal_state=temporal_state,
    )

    assert retriever.calls[0][1] >= 12
    assert len(results) == 1
    assert results[0]["text"] == "Version current in 2024."
    assert results[0]["temporal_status"] == "applicable"
    assert temporal_state["effective_date"] == "2024-06-01"
    assert temporal_state["selected_count"] == 1


def test_answer_with_rag_refuses_when_no_applicable_temporal_evidence(monkeypatch) -> None:
    retriever = _StubRetriever(
        [
            _doc(
                section="EAR-742.4",
                text="This version only applies in 2025.",
                score=0.92,
                snapshot_date="2025-01-01",
            )
        ]
    )
    monkeypatch.setattr(
        pipeline,
        "generate_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("LLM generation should be skipped for temporal refusal")
        ),
    )

    result = pipeline.answer_with_rag(
        "Does this apply?",
        retriever=retriever,
        strict_retrieval=False,
        strict_output=True,
        effective_date="2024-06-01",
    )

    assert result["label"] == "unanswerable"
    assert result["output_ok"] is True
    assert result["disabled_reason"] == "no_temporally_applicable_evidence"
    assert result["effective_date"] == "2024-06-01"
    assert result["temporal_requested"] is True
    assert result["temporal_decision"]["should_refuse"] is True
    assert result["retrieval_empty"] is True
    assert result["retrieval_empty_reason"] == "no_temporally_applicable_evidence"


def test_answer_with_rag_refuses_on_multiple_question_dates(monkeypatch) -> None:
    retriever = _StubRetriever([])
    monkeypatch.setattr(
        retriever,
        "query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Retriever should not run when the question has conflicting dates")
        ),
    )

    result = pipeline.answer_with_rag(
        "What applied on 2024-01-01 and 2025-01-01?",
        retriever=retriever,
        strict_retrieval=False,
        strict_output=True,
    )

    assert result["label"] == "unanswerable"
    assert result["disabled_reason"] == "multiple_dates_in_question"
    assert result["retrieval_empty_reason"] == "multiple_dates_in_question"
    assert result["temporal_decision"]["should_refuse"] is True
