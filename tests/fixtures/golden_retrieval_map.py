from __future__ import annotations

GOLDEN_RETRIEVAL_MAP: dict[str, list[dict[str, object]]] = {
    "gph2-ua-001": [],
    "gph2-ua-002": [],
    "gph2-ua-003": [
        {
            "section": "EAR-736.2(b)",
            "text": "General prohibitions apply to covered exports unless authorized.",
            "score": 0.42,
            "title": "General Prohibitions",
            "source_url": "https://example.test/ear/736.2b",
        }
    ],
    "gph2-ua-004": [
        {
            "section": "EAR-740.9(a)(2)",
            "text": "Section 740.9(a)(2) is reserved.",
            "score": 0.36,
            "title": "Reserved",
            "source_url": "https://example.test/ear/740.9a2",
        }
    ],
    "gph2-ua-005": [],
    "gph2-ans-001": [
        {
            "section": "EAR-736.2(b)",
            "text": "General Prohibition One: you may not proceed unless a BIS license or License Exception applies.",
            "score": 0.97,
            "title": "General Prohibitions",
            "source_url": "https://example.test/ear/736.2b",
        },
        {
            "section": "EAR-740.1",
            "text": "Part 740 describes License Exceptions and their conditions.",
            "score": 0.73,
            "title": "License Exceptions",
            "source_url": "https://example.test/ear/740.1",
        },
    ],
    "gph2-ans-002": [
        {
            "section": "EAR-740.1",
            "text": "License Exceptions authorize exports without a license when all stated conditions are met.",
            "score": 0.96,
            "title": "License Exceptions",
            "source_url": "https://example.test/ear/740.1",
        },
        {
            "section": "EAR-740.9(a)(2)",
            "text": "Section 740.9(a)(2) is reserved.",
            "score": 0.62,
            "title": "Reserved",
            "source_url": "https://example.test/ear/740.9a2",
        },
    ],
    "gph2-ans-003": [
        {
            "section": "EAR-742.4(a)(1)",
            "text": "A license is required for NS Column 1 exports to China unless an exception applies.",
            "score": 0.95,
            "title": "NS Controls",
            "source_url": "https://example.test/ear/742.4a1",
        }
    ],
    "gph2-ans-004": [
        {
            "section": "EAR-744.6(b)(3)",
            "text": "A BIS license is required for certain U.S. person support related to biological weapons activities.",
            "score": 0.94,
            "title": "U.S. Person Activities",
            "source_url": "https://example.test/ear/744.6b3",
        },
        {
            "section": "EAR-746.4(a)",
            "text": "Part 746 imposes licensing requirements for embargoed destinations.",
            "score": 0.67,
            "title": "Embargoes",
            "source_url": "https://example.test/ear/746.4a",
        },
    ],
    "gph2-ans-005": [
        {
            "section": "EAR-744.6(b)(3)",
            "text": "For covered support, a license is required for this activity.",
            "score": 0.92,
            "title": "U.S. Person Activities",
            "source_url": "https://example.test/ear/744.6b3",
        },
        {
            "section": "EAR-736.2(b)",
            "text": "General prohibitions require authorization before proceeding.",
            "score": 0.66,
            "title": "General Prohibitions",
            "source_url": "https://example.test/ear/736.2b",
        },
    ],
    "gph2-ans-006": [
        {
            "section": "EAR-736.2(b)",
            "text": "License Exceptions may authorize exports without a license when conditions are met.",
            "score": 0.91,
            "title": "General Prohibitions",
            "source_url": "https://example.test/ear/736.2b",
        },
        {
            "section": "EAR-742.4(a)(1)",
            "text": "Certain NS controls still require a license for China.",
            "score": 0.64,
            "title": "NS Controls",
            "source_url": "https://example.test/ear/742.4a1",
        },
    ],
    "gph2-ans-007": [
        {
            "section": "EAR-736.2(b)",
            "text": "You may not proceed unless a BIS license or License Exception applies.",
            "score": 0.93,
            "title": "General Prohibitions",
            "source_url": "https://example.test/ear/736.2b",
        },
        {
            "section": "EAR-744.6(b)(3)",
            "text": "A BIS license is required for covered biological-weapons support activities.",
            "score": 0.9,
            "title": "U.S. Person Activities",
            "source_url": "https://example.test/ear/744.6b3",
        },
    ],
}

__all__ = ["GOLDEN_RETRIEVAL_MAP"]
