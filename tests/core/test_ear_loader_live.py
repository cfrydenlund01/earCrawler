import pytest

from earCrawler.core.ear_loader import EARLoader


class _LiveFRClient:
    def __init__(self, detail_payload):
        self._detail_payload = detail_payload

    def search_documents(self, query):  # pragma: no cover - trivial stub
        return [{"document_number": "2026-10001"}]

    def get_document(self, doc_number):  # pragma: no cover - trivial stub
        return self._detail_payload


def test_ear_loader_live_accepts_body_html() -> None:
    loader = EARLoader(
        _LiveFRClient({"body_html": "<p>EAR update paragraph.</p>"}), query="export"
    )

    paragraphs = loader.run(live=True)

    assert paragraphs == [
        {
            "source": "ear",
            "text": "EAR update paragraph.",
            "identifier": "2026-10001:0",
        }
    ]


def test_ear_loader_live_accepts_body_text() -> None:
    loader = EARLoader(_LiveFRClient({"body_text": "Text-only content."}), query="export")

    paragraphs = loader.run(live=True)

    assert paragraphs == [
        {
            "source": "ear",
            "text": "Text-only content.",
            "identifier": "2026-10001:0",
        }
    ]


def test_ear_loader_live_rejects_missing_content_fields() -> None:
    loader = EARLoader(_LiveFRClient({"title": "No body fields"}), query="export")

    with pytest.raises(ValueError, match="missing content fields: html, body_html, body_text"):
        loader.run(live=True)
