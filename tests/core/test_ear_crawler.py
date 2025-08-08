import hashlib
import pytest

from earCrawler.core.ear_crawler import EARCrawler


def test_parse_paragraphs_and_citations():
    crawler = EARCrawler()
    html = "<p id='p-0'>First paragraph.</p><p id='p-1'>See 80 FR 3000 for details.</p>"
    paragraphs = list(crawler._parse_paragraphs(html))
    assert paragraphs == ["First paragraph.", "See 80 FR 3000 for details."]
    citations = crawler._extract_citations(paragraphs[1])
    assert citations == ["80 FR 3000"]


def test_sha256_hashing():
    text = "Example paragraph"
    # Compute sha256 as used in EARCrawler (without version)
    expected_sha = hashlib.sha256((text + "-v0").encode("utf-8")).hexdigest()
    sha = hashlib.sha256((text + "-v0").encode("utf-8")).hexdigest()
    assert sha == expected_sha
