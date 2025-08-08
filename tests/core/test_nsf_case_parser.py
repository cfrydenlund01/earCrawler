from __future__ import annotations

import hashlib

from earCrawler.core.nsf_case_parser import (
    NSFCaseParser,
    extract_entities,
)


def test_extract_entities() -> None:
    text = (
        "Dr. John Doe from University X used NSF grant DMR1234567 and Award ABC12345 for research."
    )
    entities = extract_entities(text)
    names = [e.value for e in entities if e.type == "person"]
    institutions = [e.value for e in entities if e.type == "institution"]
    grants = [e.value for e in entities if e.type == "grant"]
    # Person detection should find John Doe (case-insensitive prefix titles removed)
    assert any("John Doe" in n for n in names)
    # Institution detection should find University X
    assert any("University X" in inst for inst in institutions)
    # Grant detection should include DMR1234567 and ABC12345
    assert "DMR1234567" in grants
    assert "ABC12345" in grants


def test_parse_case_records() -> None:
    parser = NSFCaseParser()
    case_id = "NSF-C-001"
    text = (
        "This is the first paragraph of the case.\n\n"
        "Second paragraph mentions University Y with grant ABC123456.\n\n"
        "Third paragraph includes Dr. Alice Smith and the grant XYZ987654."
    )
    records = parser.parse_case(case_id, text, "http://example.com/nsf-case-001")
    assert len(records) == 3
    # Verify ordering and hashing
    for idx, rec in enumerate(records):
        assert rec.case_id == case_id
        assert rec.paragraph_index == idx
        # Ensure SHA256 reproducible
        expected_hash = hashlib.sha256(rec.text.encode("utf-8")).hexdigest()
        assert rec.sha256 == expected_hash
        # Entities in record 1 (index 1) should include institution and grant
        if idx == 1:
            entity_types = {e.type for e in rec.entities}
            assert "institution" in entity_types
            assert "grant" in entity_types
        # Entities in record 2 (index 2) should include person and grant
        if idx == 2:
            entity_types = {e.type for e in rec.entities}
            assert "person" in entity_types
            assert "grant" in entity_types
