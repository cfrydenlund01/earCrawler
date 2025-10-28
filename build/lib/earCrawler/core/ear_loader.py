"""EAR paragraph loader implementing :class:`CorpusLoader`."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator, Iterable

import json
from bs4 import BeautifulSoup

from api_clients.federalregister_client import FederalRegisterClient
from .corpus_loader import CorpusLoader


class EARLoader(CorpusLoader):
    """Load paragraphs from the Federal Register EAR documents."""

    def __init__(self, client: FederalRegisterClient, query: str) -> None:
        self.client = client
        self.query = query

    def iterate_paragraphs(self) -> Iterator[Dict[str, object]]:
        for doc in self.client.search_documents(self.query):
            doc_number = str(doc.get("document_number", ""))
            detail = self.client.get_document(doc_number)
            html = detail.get("html", "")
            yield from self._parse_document(doc_number, html)

    def _parse_document(self, doc_number: str, html: str) -> Iterable[Dict[str, object]]:
        """Yield paragraph dictionaries from a document's HTML."""
        soup = BeautifulSoup(html, "html.parser")
        for idx, p in enumerate(soup.find_all("p")):
            text = " ".join(p.get_text(" ").split())
            if not text:
                continue
            yield {
                "source": "ear",
                "text": text,
                "identifier": f"{doc_number}:{idx}",
            }

    def run(
        self,
        fixtures_dir: Path | None = None,
        live: bool = False,
        output_dir: str | None = None,
    ) -> list[Dict[str, object]]:
        """Return paragraphs either from live crawl or local fixtures."""
        if not live and fixtures_dir:
            return list(self._load_from_fixtures(fixtures_dir, output_dir))
        return list(self.iterate_paragraphs())

    def _load_from_fixtures(
        self, fixtures_dir: Path, output_dir: str | None = None
    ) -> Iterator[Dict[str, object]]:
        """Yield paragraphs from ``fixtures_dir/ear_*.json`` or ``.html`` files."""
        for path in sorted(Path(fixtures_dir).glob("ear_*.json")):
            with path.open("r", encoding="utf-8") as fh:
                doc = json.load(fh)
            doc_number = str(doc.get("document_number", path.stem))
            html = doc.get("html", "")
            yield from self._parse_document(doc_number, html)
        for path in sorted(Path(fixtures_dir).glob("ear_*.html")):
            html = path.read_text(encoding="utf-8")
            stem = path.stem.split("ear_", 1)[-1]
            yield from self._parse_document(stem, html)
