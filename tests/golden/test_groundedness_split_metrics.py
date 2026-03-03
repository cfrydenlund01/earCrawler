from __future__ import annotations

import pytest

from earCrawler.eval.groundedness_gates import evaluate_groundedness_signals


@pytest.mark.parametrize(
    ("case_id", "result", "expected"),
    [
        (
            "support-001",
            {
                "answer_text": (
                    "Yes. A BIS license is required for this activity; internal review is complete."
                ),
                "citations": [
                    {
                        "section_id": "EAR-744.6(b)(3)",
                        "quote": (
                            "A BIS license is required for certain U.S. person support related "
                            "to biological weapons activities."
                        ),
                    }
                ],
                "raw_context": (
                    "[EAR-744.6(b)(3)] A BIS license is required for certain U.S. person "
                    "support related to biological weapons activities."
                ),
            },
            {"valid": 1.0, "supported": 0.5, "overclaim": 0.5, "reason": "claim_without_linked_citation"},
        ),
        (
            "support-002",
            {
                "answer_text": "Yes. A BIS license or License Exception is required before proceeding.",
                "citations": [
                    {
                        "section_id": "EAR-740.1",
                        "quote": "You may not proceed unless a BIS license or License Exception applies.",
                    }
                ],
                "raw_context": (
                    "[EAR-736.2(b)] You may not proceed unless a BIS license or License Exception applies.\n\n"
                    "[EAR-740.1] License Exceptions authorize exports without a license when all stated "
                    "conditions are met."
                ),
            },
            {"valid": 1.0, "supported": 0.0, "overclaim": 1.0, "reason": "claim_linked_citation_not_supported"},
        ),
        (
            "overclaim-001",
            {
                "answer_text": (
                    "Yes. A license is required for NS Column 1 exports to China unless an "
                    "exception applies. Internal screening is complete."
                ),
                "citations": [
                    {
                        "section_id": "EAR-742.4(a)(1)",
                        "quote": "A license is required for NS Column 1 exports to China unless an exception applies.",
                    }
                ],
                "raw_context": (
                    "[EAR-742.4(a)(1)] A license is required for NS Column 1 exports to China "
                    "unless an exception applies."
                ),
            },
            {"valid": 1.0, "supported": 0.5, "overclaim": 0.5, "reason": "claim_without_linked_citation"},
        ),
    ],
)
def test_groundedness_split_metrics(case_id: str, result: dict, expected: dict[str, object]) -> None:
    evaluation = evaluate_groundedness_signals(result)

    assert evaluation["citation_validity"]["valid_citation_rate"] == pytest.approx(expected["valid"])
    assert evaluation["citation_support"]["supported_rate"] == pytest.approx(expected["supported"])
    assert evaluation["overclaim"]["overclaim_rate"] == pytest.approx(expected["overclaim"])
    assert any(
        expected["reason"] in (claim.get("reasons") or [])
        for claim in evaluation["citation_support"]["claims"]
    ), case_id
