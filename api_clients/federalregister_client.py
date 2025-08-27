"""Federal Register API client for EAR text retrieval."""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Dict, List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from earCrawler.utils.secure_store import get_secret
from earCrawler.utils.http_cache import HTTPCache


class FederalRegisterError(Exception):
    """Raised for Federal Register client errors or invalid responses."""


class FederalRegisterClient:
    """Client for the Federal Register API."""

    BASE_URL = "https://api.federalregister.gov/v1"

    def __init__(self, *, session: requests.Session | None = None, cache_dir: Path | None = None) -> None:
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.user_agent = get_secret("FEDERALREGISTER_USER_AGENT", fallback="earCrawler/0.9")
        self.cache = HTTPCache(cache_dir or Path(".cache/api/federalregister"))

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _get_json(self, url: str, params: dict[str, str]) -> dict:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        resp = self.cache.get(self.session, url, params, headers=headers)
        resp.raise_for_status()
        if "application/json" not in resp.headers.get("Content-Type", ""):
            raise FederalRegisterError(f"Non-JSON response from FR at {resp.url}")
        try:
            return resp.json()
        except ValueError as exc:  # pragma: no cover
            raise FederalRegisterError("Invalid JSON from Federal Register") from exc

    def get_ear_articles(self, term: str, *, per_page: int = 5) -> List[Dict[str, str]]:
        """Return normalized EAR article records for ``term``."""
        url = f"{self.BASE_URL}/documents"
        params = {"per_page": str(per_page), "conditions[term]": term}
        data = self._get_json(url, params)
        results: List[Dict[str, str]] = []
        for doc in data.get("results", []):
            text = self._clean_text(doc.get("body_html") or doc.get("body_text") or "")
            results.append(
                {
                    "id": str(doc.get("document_number") or doc.get("id") or ""),
                    "title": doc.get("title", ""),
                    "publication_date": doc.get("publication_date", ""),
                    "source_url": doc.get("html_url") or doc.get("url") or "",
                    "text": text,
                }
            )
        return results

    def get_article_text(self, doc_id: str) -> str:
        """Return cleaned text for a Federal Register document."""
        url = f"{self.BASE_URL}/documents/{doc_id}"
        data = self._get_json(url, params={})
        return self._clean_text(data.get("body_html") or data.get("body_text") or "")

    # Backwards compatible wrappers
    def search_documents(self, query: str, per_page: int = 100):
        url = f"{self.BASE_URL}/documents"
        params = {"conditions[any]": query, "per_page": str(per_page)}
        data = self._get_json(url, params)
        return data.get("results", [])

    def get_document(self, doc_number: str):
        url = f"{self.BASE_URL}/documents/{doc_number}"
        return self._get_json(url, params={})

    def get_ear_text(self, citation: str) -> str:
        data = self.get_document(citation)
        return data.get("body_html", "")

    @staticmethod
    def _clean_text(html: str) -> str:
        text = re.sub("<[^>]+>", " ", html)
        text = unescape(text)
        return " ".join(text.split())
