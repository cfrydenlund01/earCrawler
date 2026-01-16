from __future__ import annotations

from scripts.eval import eval_rag_llm


def test_answer_scoring_exact_requires_exact_match() -> None:
    assert eval_rag_llm._answer_is_correct("Yes.", "Yes.", mode="exact") is True
    assert eval_rag_llm._answer_is_correct("Yes.", "yes.", mode="exact") is False


def test_answer_scoring_normalized_ignores_case_and_punct() -> None:
    assert eval_rag_llm._answer_is_correct("Yes.", " yes ", mode="normalized") is True
    assert (
        eval_rag_llm._answer_is_correct(
            "Answer: Yes!", "final answer: yes", mode="normalized"
        )
        is True
    )


def test_answer_scoring_semantic_uses_threshold() -> None:
    gt = "Yes. A license is required for that activity."
    pred = "Yes, a license is required."
    assert (
        eval_rag_llm._answer_is_correct(
            gt, pred, mode="semantic", semantic_threshold=0.6
        )
        is True
    )
    assert (
        eval_rag_llm._answer_is_correct(
            gt, pred, mode="semantic", semantic_threshold=0.99
        )
        is False
    )
