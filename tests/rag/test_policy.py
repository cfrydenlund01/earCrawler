from __future__ import annotations

from earCrawler.rag import policy



def test_policy_preserves_pipeline_empty_retrieval_behavior() -> None:
    decision = policy.evaluate_generation_policy(
        docs=[],
        contexts=[],
        temporal_state={},
        refuse_on_empty=False,
    )

    assert decision.should_refuse is False
    assert decision.disabled_reason is None
    assert decision.refusal_payload is None



def test_policy_refuses_temporal_ambiguity() -> None:
    decision = policy.evaluate_generation_policy(
        docs=[],
        contexts=[],
        temporal_state={
            "should_refuse": True,
            "refusal_reason": "temporal_evidence_ambiguous",
            "effective_date": "2024-06-01",
        },
        refuse_on_empty=True,
    )

    assert decision.should_refuse is True
    assert decision.disabled_reason == "temporal_evidence_ambiguous"
    assert decision.refusal_payload is not None
    assert decision.refusal_payload["label"] == "unanswerable"
    assert "2024-06-01" in (decision.refusal_payload["answer_text"] or "")
