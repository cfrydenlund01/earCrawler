"""EAR paragraph loader implementing :class:`CorpusLoader`."""

from __future__ import annotations

from typing import Dict, Iterator

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
