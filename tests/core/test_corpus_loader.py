from pathlib import Path

from earCrawler.core.ear_loader import EARLoader
from earCrawler.core.nsf_loader import NSFLoader


class _DummyFRClient:
    def search_documents(self, query):  # pragma: no cover - simple stub
        yield {"document_number": "1"}

    def get_document(self, doc_number):  # pragma: no cover - simple stub
        return {"html": "<p>Hello</p>"}


class _DummyParser:
    def run(self, fixtures_dir: Path, live: bool = False):  # pragma: no cover
        return [{"case_number": "c1", "paragraphs": ["a", "b"]}]


def test_loaders_output_shape(tmp_path: Path) -> None:
    ear_loader = EARLoader(_DummyFRClient(), query="export")
    nsf_loader = NSFLoader(_DummyParser(), tmp_path)
    for loader in (ear_loader, nsf_loader):
        paragraphs = loader.load_paragraphs()
        assert paragraphs
        for para in paragraphs:
            assert set(para.keys()) == {"source", "text", "identifier"}
