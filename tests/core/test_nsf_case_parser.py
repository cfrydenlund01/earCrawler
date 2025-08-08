from __future__ import annotations

from pathlib import Path

from earCrawler.core.nsf_case_parser import NSFCaseParser


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_run_parses_case() -> None:
    parser = NSFCaseParser()
    cases = parser.run(FIXTURES, live=False)
    assert len(cases) == 1
    case = cases[0]
    assert case["case_number"] == "NSF-001"
    assert len(case["paragraphs"]) == 2
    for para in case["paragraphs"]:
        assert len(para) >= 30
    assert set(["R01-ABC123", "University of Testing", "John Smith"]) <= set(
        case["entities"]
    )
    expected_hash = NSFCaseParser.hash_text("\n".join(case["paragraphs"]))
    assert case["hash"] == expected_hash
