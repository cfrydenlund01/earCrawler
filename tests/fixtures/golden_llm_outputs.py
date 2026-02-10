from __future__ import annotations

import json


def _render(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


GOLDEN_LLM_OUTPUTS: dict[str, str] = {
    "gph2-ua-001": _render(
        {
            "label": "unanswerable",
            "answer_text": "Insufficient information to determine. Need ITAR scope and item classification details.",
            "justification": "The retrieved EAR context does not cover ITAR Category XI licensing.",
            "citations": [],
            "evidence_okay": {"ok": True, "reasons": ["no_grounded_quote_for_key_claim"]},
            "assumptions": [],
        }
    ),
    "gph2-ua-002": _render(
        {
            "label": "unanswerable",
            "answer_text": "Insufficient information to determine. Need de minimis rules and destination-specific thresholds.",
            "justification": "No excerpt states the requested de minimis threshold.",
            "citations": [],
            "evidence_okay": {"ok": True, "reasons": ["no_grounded_quote_for_key_claim"]},
            "assumptions": [],
        }
    ),
    "gph2-ua-003": _render(
        {
            "label": "unanswerable",
            "answer_text": "Insufficient information to determine. Need ECCN details and applicable STA conditions.",
            "justification": "The retrieved text does not establish STA eligibility for the scenario.",
            "citations": [],
            "evidence_okay": {"ok": True, "reasons": ["no_grounded_quote_for_key_claim"]},
            "assumptions": [],
        }
    ),
    "gph2-ua-004": _render(
        {
            "label": "unanswerable",
            "answer_text": "Insufficient information to determine. Need ECCN, destination, and end-use details.",
            "justification": "The retrieved context does not contain the required encryption-control determination.",
            "citations": [],
            "evidence_okay": {"ok": True, "reasons": ["no_grounded_quote_for_key_claim"]},
            "assumptions": [],
        }
    ),
    "gph2-ua-005": _render(
        {
            "label": "unanswerable",
            "answer_text": "Insufficient information to determine. Need classification records and destination controls.",
            "justification": "No cited excerpt supports classifying ECCN 9A610 in this context.",
            "citations": [],
            "evidence_okay": {"ok": True, "reasons": ["no_grounded_quote_for_key_claim"]},
            "assumptions": [],
        }
    ),
    "gph2-ans-001": _render(
        {
            "label": "true",
            "answer_text": "Yes. A license or qualifying License Exception is required before proceeding.",
            "justification": "The general prohibition text requires authorization before covered exports proceed.",
            "citations": [
                {
                    "section_id": "EAR-736.2(b)",
                    "quote": "you may not proceed unless a BIS license or License Exception applies.",
                    "span_id": "736.2(b)",
                }
            ],
            "evidence_okay": {
                "ok": True,
                "reasons": ["citation_quote_is_substring_of_context"],
            },
            "assumptions": [],
        }
    ),
    "gph2-ans-002": _render(
        {
            "label": "true",
            "answer_text": "Yes. A License Exception can authorize export without a license when conditions are met.",
            "justification": "The cited Part 740 excerpt explicitly permits no-license exports under exception conditions.",
            "citations": [
                {
                    "section_id": "EAR-740.1",
                    "quote": "License Exceptions authorize exports without a license when all stated conditions are met.",
                    "span_id": "740.1",
                }
            ],
            "evidence_okay": {
                "ok": True,
                "reasons": ["citation_quote_is_substring_of_context"],
            },
            "assumptions": [],
        }
    ),
    "gph2-ans-003": _render(
        {
            "label": "true",
            "answer_text": "Yes. The cited NS-control section requires a license for China.",
            "justification": "The excerpt states a license requirement for NS Column 1 exports to China.",
            "citations": [
                {
                    "section_id": "EAR-742.4(a)(1)",
                    "quote": "A license is required for NS Column 1 exports to China unless an exception applies.",
                    "span_id": "742.4(a)(1)",
                }
            ],
            "evidence_okay": {
                "ok": True,
                "reasons": ["citation_quote_is_substring_of_context"],
            },
            "assumptions": [],
        }
    ),
    "gph2-ans-004": _render(
        {
            "label": "true",
            "answer_text": "Yes. The cited provision requires a BIS license for the described support activity.",
            "justification": "The excerpt explicitly imposes a BIS license requirement for covered support.",
            "citations": [
                {
                    "section_id": "EAR-744.6(b)(3)",
                    "quote": "A BIS license is required for certain U.S. person support related to biological weapons activities.",
                    "span_id": "744.6(b)(3)",
                }
            ],
            "evidence_okay": {
                "ok": True,
                "reasons": ["citation_quote_is_substring_of_context"],
            },
            "assumptions": [],
        }
    ),
    "gph2-ans-005": _render(
        {
            "label": "true",
            "answer_text": "Yes. The scenario requires a license under the cited embargo control.",
            "justification": "The quote supports a license requirement for the described activity.",
            "citations": [
                {
                    "section_id": "EAR-746.4(a)",
                    "quote": "a license is required for this activity.",
                    "span_id": "746.4(a)",
                }
            ],
            "evidence_okay": {
                "ok": True,
                "reasons": ["citation_quote_is_substring_of_context"],
            },
            "assumptions": [],
        }
    ),
    "gph2-ans-006": _render(
        {
            "label": "false",
            "answer_text": "False. License Exceptions can authorize exports without a license when conditions are met.",
            "justification": "The cited language directly contradicts the statement that exceptions can never authorize export.",
            "citations": [
                {
                    "section_id": "EAR-740.1",
                    "quote": "License Exceptions may authorize exports without a license when conditions are met.",
                    "span_id": "740.1",
                }
            ],
            "evidence_okay": {
                "ok": True,
                "reasons": ["citation_quote_is_substring_of_context"],
            },
            "assumptions": [],
        }
    ),
    "gph2-ans-007": _render(
        {
            "label": "true",
            "answer_text": "Yes. Both the general-prohibition authorization rule and the biological-weapons support license rule apply.",
            "justification": "Both cited excerpts are needed to support the joint obligation.",
            "citations": [
                {
                    "section_id": "EAR-736.2(b)",
                    "quote": "You may not proceed unless a BIS license or License Exception applies.",
                    "span_id": "736.2(b)",
                },
                {
                    "section_id": "EAR-744.6(b)(3)",
                    "quote": "A BIS license is required for covered biological-weapons support activities.",
                    "span_id": "744.6(b)(3)",
                },
            ],
            "evidence_okay": {
                "ok": True,
                "reasons": ["citation_quote_is_substring_of_context"],
            },
            "assumptions": [],
        }
    ),
}

__all__ = ["GOLDEN_LLM_OUTPUTS"]
