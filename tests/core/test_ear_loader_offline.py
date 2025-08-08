from pathlib import Path
from unittest.mock import Mock

from earCrawler.core.ear_loader import EARLoader


def test_ear_loader_offline(monkeypatch) -> None:
    client = Mock()
    loader = EARLoader(client, query="export administration regulations")
    fixtures = Path("tests/fixtures")
    paragraphs = loader.run(fixtures_dir=fixtures, live=False, output_dir="data")
    expected = [
        {"source": "ear", "text": "Paragraph one.", "identifier": "123:0"},
        {"source": "ear", "text": "Paragraph two.", "identifier": "123:1"},
    ]
    assert paragraphs == expected
    client.search_documents.assert_not_called()
    client.get_document.assert_not_called()
