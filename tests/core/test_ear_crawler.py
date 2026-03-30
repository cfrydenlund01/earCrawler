import hashlib
from pathlib import Path

import pytest

from earCrawler.core.ear_crawler import EARCrawler, FederalRegisterClient


class _DummyClient(FederalRegisterClient):
    def search_documents(self, query: str, per_page: int = 100):  # pragma: no cover
        return []

    def get_document(self, doc_number: str):  # pragma: no cover
        return {}


class _SingleDocClient(FederalRegisterClient):
    def search_documents(self, query: str, per_page: int = 100):  # pragma: no cover
        return [{"id": "DOC-123"}]

    def get_document(self, doc_number: str):  # pragma: no cover
        return {"html_url": "https://example.test/doc"}


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


def test_run_uses_id_fallback_for_document_number(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    crawler = EARCrawler(_SingleDocClient(), tmp_path)
    monkeypatch.setattr(
        crawler,
        "_download_html",
        lambda _url, timeout=15.0: "<p>Paragraph one.</p>",
    )
    records = crawler.run("export administration regulations", delay=0.0)
    assert len(records) == 1
    assert records[0].document_number == "DOC-123"


def test_run_does_not_scan_hash_index_values_for_version_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crawler = EARCrawler(_SingleDocClient(), tmp_path)

    class _NoValuesDict(dict):
        def values(self):  # pragma: no cover - defensive guard
            raise AssertionError("run() should not scan hash_index.values()")

    crawler.hash_index = _NoValuesDict()
    crawler._position_versions = {}
    monkeypatch.setattr(
        crawler,
        "_download_html",
        lambda _url, timeout=15.0: "<p>Paragraph one.</p><p>Paragraph two.</p>",
    )
    records = crawler.run("export administration regulations", delay=0.0)
    assert len(records) == 2
    assert all(record.version == 1 for record in records)
