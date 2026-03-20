from __future__ import annotations

from pathlib import Path

from api_clients.upstream_status import UpstreamResult, UpstreamStatus
from earCrawler.corpus.metadata import EarMetadataResolver


def test_ear_metadata_resolver_uses_typed_document_result() -> None:
    captured: list[UpstreamStatus] = []

    class _StubClient:
        def get_document_result(self, doc_number: str):
            return UpstreamResult(
                data={
                    "html_url": f"https://www.federalregister.gov/documents/{doc_number}",
                    "publication_date": "2026-03-20",
                    "cfr_references": [{"citation": "15 CFR 736"}],
                },
                status=UpstreamStatus(
                    source="federalregister",
                    operation="get_document",
                    state="retry_exhausted",
                    retry_attempts=3,
                ),
            )

    resolver = EarMetadataResolver(
        Path("tests/fixtures"),
        allow_network=True,
        status_hook=captured.append,
        client_factory=lambda: _StubClient(),
    )
    meta = resolver.resolve("2026-10001")

    assert meta.source_url == "https://www.federalregister.gov/documents/2026-10001"
    assert meta.date == "2026-03-20"
    assert meta.section == "15 CFR 736"
    assert captured
    assert captured[0].state == "retry_exhausted"
