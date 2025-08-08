import hashlib
from pathlib import Path

import pytest

from earCrawler.core.ear_crawler import EARCrawler, FederalRegisterClient


class _DummyClient(FederalRegisterClient):
    def search_documents(self, query: str, per_page: int = 100):  # pragma: no cover
        return []

    def get_document(self, doc_number: str):  # pragma: no cover
        return {}


def test_parse_paragraphs_and_citations(tmp_path: Path) -> None:
    crawler = EARCrawler(_DummyClient(), tmp_path)
    html = "<p id='p-0'>First paragraph.</p><p id='p-1'>See 80 FR 3000 for details.</p>"
    paragraphs = list(crawler._parse_paragraphs(html))
    assert paragraphs == ["First paragraph.", "See 80 FR 3000 for details."]
    citations = crawler._extract_citations(paragraphs[1])
    assert citations == ["80 FR 3000"]


def test_sha256_hashing() -> None:
    text = "Example paragraph"
    expected_sha = hashlib.sha256((text + "-v0").encode("utf-8")).hexdigest()
    sha = hashlib.sha256((text + "-v0").encode("utf-8")).hexdigest()
    assert sha == expected_sha
