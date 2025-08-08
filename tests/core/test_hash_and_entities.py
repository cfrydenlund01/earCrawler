from __future__ import annotations

from earCrawler.core.nsf_case_parser import NSFCaseParser


def test_hash_deterministic() -> None:
    text = "some sample text"
    h1 = NSFCaseParser.hash_text(text)
    h2 = NSFCaseParser.hash_text(text)
    assert h1 == h2


def test_entity_regex() -> None:
    text = (
        "John Smith from University of Testing received GRANT R01-ABC123 for research."
    )
    entities = NSFCaseParser.extract_entities(text)
    assert "John Smith" in entities
    assert "University of Testing" in entities
    assert "R01-ABC123" in entities
