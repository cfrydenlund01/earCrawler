"""Federal Register API client for EAR text retrieval."""

from __future__ import annotations

import os
import re
from html import unescape
from pathlib import Path
from typing import Dict, List

import requests
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from earCrawler.utils.secure_store import get_secret
from earCrawler.utils.http_cache import HTTPCache
from earCrawler.utils import budget
from earCrawler.utils.log_json import JsonLogger


_VARY_HEADERS = ("Accept", "User-Agent")
_logger = JsonLogger("federalregister-client")


def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    wait_time = (
        getattr(retry_state.next_action, "sleep", None)
        if retry_state.next_action
        else None
    )
    url = ""
    if len(retry_state.args) >= 2:
        url = str(retry_state.args[1])
    _logger.warning(
        "api.retry",
        url=url,
        attempt=retry_state.attempt_number,
        wait_seconds=wait_time,
        error=str(exc) if exc else None,
    )


class FederalRegisterError(Exception):
    """Raised for Federal Register client errors or invalid responses."""


class FederalRegisterClient:
    """Client for the Federal Register API."""

    # Federal Register JSON API base.
    # The stable API host is ``api.federalregister.gov``; ``www`` is used only
    # as a fallback when the API host is blocked and returns HTML.
    BASE_URL = "https://api.federalregister.gov/v1"

    def __init__(
        self, *, session: requests.Session | None = None, cache_dir: Path | None = None
    ) -> None:
        self.session = session or requests.Session()
        self._owns_session = session is None
        self.session.trust_env = False
        self.user_agent = get_secret(
            "FEDERALREGISTER_USER_AGENT", fallback="earCrawler/0.9"
        )
        base_url_override = os.getenv("FR_BASE_URL")
        if base_url_override:
            self.BASE_URL = base_url_override.rstrip("/")
        ttl_env = os.getenv("FR_CACHE_TTL_SECONDS")
        ttl_seconds = int(ttl_env) if ttl_env else None
        max_env = os.getenv("FR_CACHE_MAX_ENTRIES")
        max_entries = int(max_env) if max_env else 4096
        self.cache = HTTPCache(
            cache_dir or Path(".cache/api/federalregister"),
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
        )
        env_limit = os.getenv("FR_MAX_CALLS")
        self.request_limit = int(env_limit) if env_limit else None
        _logger.info(
            "api.client.init",
            user_agent=self.user_agent,
            request_limit=self.request_limit,
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1),
        retry=retry_if_exception_type(requests.RequestException),
        before_sleep=_log_retry,
    )
    def _get_json(self, url: str, params: dict[str, str]) -> dict:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        _logger.info("api.request", url=url, params=params, limit=self.request_limit)
        try:
            with budget.consume("federalregister", self.request_limit):
                resp = self.cache.get(
                    self.session,
                    url,
                    params,
                    headers=headers,
                    vary_headers=_VARY_HEADERS,
                )
        except budget.BudgetExceededError:
            _logger.error("api.budget_exceeded", url=url, limit=self.request_limit)
            raise
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            # Some FR edges return an HTML anti-bot page (e.g., https://unblock.federalregister.gov)
            # when the api.* host is blocked. Retry once against the www host if we have not already.
            alt_host = "https://www.federalregister.gov/api/v1"
            if not resp.url.startswith(alt_host):
                alt_url = resp.url.replace(
                    "https://api.federalregister.gov/v1", alt_host
                )
                _logger.warning(
                    "api.invalid_content_type_retry",
                    url=resp.url,
                    alt_url=alt_url,
                    content_type=content_type,
                )
                return self._get_json(alt_url, params)
            _logger.error(
                "api.invalid_content_type",
                url=resp.url,
                content_type=content_type,
            )
            raise FederalRegisterError(f"Non-JSON response from FR at {resp.url}")
        try:
            payload = resp.json()
        except ValueError as exc:  # pragma: no cover
            _logger.error("api.invalid_json", url=url, error=str(exc))
            raise FederalRegisterError("Invalid JSON from Federal Register") from exc
        _logger.info(
            "api.response",
            url=url,
            status=resp.status_code,
            cache="hit" if getattr(resp, "from_cache", False) else "miss",
            result_count=(
                len(payload.get("results", [])) if isinstance(payload, dict) else None
            ),
        )
        return payload

    def get_ear_articles(self, term: str, *, per_page: int = 5) -> List[Dict[str, str]]:
        """Return normalized EAR article records for ``term``."""
        url = f"{self.BASE_URL}/documents"
        params = {"per_page": str(per_page), "conditions[term]": term}
        try:
            data = self._get_json(url, params)
        except requests.RequestException as exc:
            _logger.error("api.request_failed", url=url, term=term, error=str(exc))
            return []
        results: List[Dict[str, str]] = []
        for doc in data.get("results", []):
            doc_id = str(doc.get("document_number") or doc.get("id") or "")
            text_raw = doc.get("body_html") or doc.get("body_text") or ""
            if not text_raw and doc_id:
                # List results often omit body text; fetch the detail JSON when needed.
                detail = self.get_document(doc_id) or {}
                text_raw = detail.get("body_html") or detail.get("body_text") or ""
            if not text_raw:
                text_raw = (
                    doc.get("abstract") or " ".join(doc.get("excerpts") or []) or ""
                )
            text = self._clean_text(text_raw)
            results.append(
                {
                    "id": doc_id,
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
        try:
            data = self._get_json(url, params={})
        except requests.RequestException as exc:
            _logger.error(
                "api.request_failed", url=url, document=doc_id, error=str(exc)
            )
            return ""
        return self._clean_text(data.get("body_html") or data.get("body_text") or "")

    # Backwards compatible wrappers
    def search_documents(
        self,
        query: str,
        per_page: int = 100,
        page: int | None = None,
    ) -> List[Dict]:
        url = f"{self.BASE_URL}/documents"
        params = {"conditions[any]": query, "per_page": str(per_page)}
        if page is not None:
            params["page"] = str(page)
        try:
            data = self._get_json(url, params)
        except requests.RequestException as exc:
            _logger.error(
                "api.request_failed", url=url, query=query, page=page, error=str(exc)
            )
            return []
        return data.get("results", [])

    def get_document(self, doc_number: str):
        url = f"{self.BASE_URL}/documents/{doc_number}"
        try:
            return self._get_json(url, params={})
        except requests.RequestException as exc:
            _logger.error(
                "api.request_failed", url=url, document=doc_number, error=str(exc)
            )
            return {}

    def get_ear_text(self, citation: str) -> str:
        data = self.get_document(citation)
        return data.get("body_html", "")

    # Resource lifecycle -------------------------------------------------
    def close(self) -> None:
        try:
            if self._owns_session:
                self.session.close()
        except Exception:
            pass

    @staticmethod
    def _clean_text(html: str) -> str:
        text = re.sub("<[^>]+>", " ", html)
        text = unescape(text)
        return " ".join(text.split())


def search_documents(
    query: str,
    *,
    per_page: int = 100,
    page: int | None = None,
) -> dict:
    """Convenience wrapper returning a JSON response payload."""

    client = FederalRegisterClient()
    results = client.search_documents(query, per_page=per_page, page=page)
    return {"results": results}
