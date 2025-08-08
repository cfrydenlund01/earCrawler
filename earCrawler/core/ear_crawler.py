"""Tools for crawling and versioning EAR paragraphs from the Federal Register.

The EARCrawler class encapsulates the logic required to incrementally download Export Administration Regulations (EAR) text
from the Federal Register API, normalise paragraphs, compute a cryptographic hash of each paragraph for change detection, and index
embedded Federal Register citations.  It is designed to operate incrementally by persisting hashes of previously observed paragraphs
between runs, thereby producing new records only when the text changes.

The crawler relies on the api_clients.federalregister_client.FederalRegisterClient to perform the underlying API calls.  Documents are
fetched via the search_documents method using a free‑text query.  For each returned document the crawler attempts to resolve the
html_url or body_html_url field and download the full HTML.  Paragraphs are extracted with BeautifulSoup, normalised to strip extraneous whitespace,
hashed with SHA-256 and returned as ParagraphRecord objects.

Federal Register citations embedded in the paragraph text (e.g. "85 FR 12345") are extracted via regular expressions to support later link analysis.

"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

import requests
from bs4 import BeautifulSoup

try:
    from api_clients.federalregister_client import FederalRegisterClient, FederalRegisterError  # type: ignore
except Exception:
    class FederalRegisterError(Exception):
        """Fallback error used when FederalRegisterClient cannot be imported."""
    class FederalRegisterClient:
        """Fallback dummy Federal Register client used during docs/tests."""
        def search_documents(self, query: str, per_page: int = 100) -> Iterable[Dict]:
            return []
        def get_document(self, doc_number: str) -> Dict:
            return {}

ParagraphCitation = str

@dataclass
class ParagraphRecord:
    document_number: str
    paragraph_index: int
    text: str
    sha256: str
    citations: List[ParagraphCitation]
    scraped_at: str
    version: int = 1

class EARCrawler:
    """Incrementally crawl EAR paragraphs from the Federal Register."""
    def __init__(
        self,
        federal_client: FederalRegisterClient,
        storage_dir: Path,
        citation_regex: Optional[re.Pattern[str]] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.client = federal_client
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.citation_regex = citation_regex or re.compile(r"\b\d{1,3}\s+FR\s+\d{1,6}\b", re.IGNORECASE)
        self.session = session or requests.Session()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.paragraphs_path = self.storage_dir / "ear_paragraphs.jsonl"
        self.index_path = self.storage_dir / "hash_index.json"
        self.hash_index: Dict[str, ParagraphRecord] = {}
        self._load_index()

    def _load_index(self) -> None:
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                for sha, rec in data.items():
                    self.hash_index[sha] = ParagraphRecord(**rec)
            except Exception as exc:
                self.logger.warning("Failed to load hash index: %s", exc)

    def _save_index(self) -> None:
        serialisable = {sha: asdict(rec) for sha, rec in self.hash_index.items()}
        self.index_path.write_text(json.dumps(serialisable, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalise_text(self, text: str) -> str:
        return " ".join(text.strip().split())

    def _extract_citations(self, text: str) -> List[ParagraphCitation]:
        return [match.group().strip() for match in self.citation_regex.finditer(text)]

    def _download_html(self, url: str, timeout: float = 15.0) -> Optional[str]:
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            self.logger.warning("Failed to fetch HTML %s: %s", url, exc)
            return None

    def _parse_paragraphs(self, html: str) -> Iterator[str]:
        soup = BeautifulSoup(html, "html.parser")
        for p in soup.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            if text:
                yield self._normalise_text(text)

    def run(self, query: str, per_page: int = 100, delay: float = 1.0) -> List[ParagraphRecord]:
        new_records: List[ParagraphRecord] = []
        try:
            documents_iter = self.client.search_documents(query, per_page=per_page)
        except Exception as exc:
            self.logger.warning("Document search failed for query '%s': %s", query, exc)
            return []

        for doc in documents_iter:
            doc_number = str(doc.get("document_number") or doc.get("document_number"))
            if not doc_number:
                self.logger.warning("Skipping document missing 'document_number': %s", doc)
                continue
            try:
                detail = self.client.get_document(doc_number)
            except Exception as exc:
                self.logger.warning("Failed to fetch document %s: %s", doc_number, exc)
                continue
            html_url: Optional[str] = None
            for key in ("body_html_url", "html_url", "html_url_publication", "html_url_download"):
                val = detail.get(key)
                if isinstance(val, str) and val:
                    html_url = val
                    break
            if not html_url:
                self.logger.warning("No HTML URL found for document %s", doc_number)
                continue
            html = self._download_html(html_url)
            if not html:
                continue
            paragraphs = list(self._parse_paragraphs(html))
            for idx, text in enumerate(paragraphs):
                sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                citations = self._extract_citations(text)
                if sha in self.hash_index:
                    continue
                version = 1
                for existing in self.hash_index.values():
                    if existing.document_number == doc_number and existing.paragraph_index == idx:
                        version = existing.version + 1
                        break
                record = ParagraphRecord(
                    document_number=doc_number,
                    paragraph_index=idx,
                    text=text,
                    sha256=sha,
                    citations=citations,
                    scraped_at=datetime.utcnow().isoformat(sep="T", timespec="seconds") + "Z",
                    version=version,
                )
                new_records.append(record)
                self.hash_index[sha] = record
            if delay > 0:
                time.sleep(delay)
        if new_records:
            with self.paragraphs_path.open("a", encoding="utf-8") as f:
                for rec in new_records:
                    f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
            self._save_index()
        return new_records
