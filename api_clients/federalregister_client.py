"""eCFR API client for Title 15 (EAR) text retrieval.

Historically this repo used the Federal Register "documents" API as a proxy
corpus source. We now use the eCFR API instead. The public interface is kept
compatible to minimize downstream changes.
"""

from __future__ import annotations

import os
import re
from html import unescape
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote

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
_logger = JsonLogger("ecfr-client")


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
    """Raised for eCFR client errors or invalid responses."""


class FederalRegisterClient:
    """Client for the eCFR API (Title 15)."""

    # eCFR JSON API base. Overrides via ECFR_BASE_URL or legacy FR_BASE_URL.
    BASE_URL = "https://api.federalregister.gov/v1/ecfr"

    def __init__(
        self, *, session: requests.Session | None = None, cache_dir: Path | None = None
    ) -> None:
        self.session = session or requests.Session()
        self._owns_session = session is None
        self.session.trust_env = False
        self.user_agent = get_secret(
            "FEDERALREGISTER_USER_AGENT", fallback="earCrawler/0.9"
        )
        self.api_key = get_secret("ECFR_API_KEY", fallback="")
        if not self.api_key:
            # eCFR uses the same API key used for Federal Register access.
            self.api_key = get_secret("FEDREG_API_KEY", fallback="")
        base_url_override = os.getenv("ECFR_BASE_URL") or os.getenv("FR_BASE_URL")
        if base_url_override:
            self.BASE_URL = base_url_override.rstrip("/")
        ttl_env = os.getenv("ECFR_CACHE_TTL_SECONDS") or os.getenv("FR_CACHE_TTL_SECONDS")
        ttl_seconds = int(ttl_env) if ttl_env else None
        max_env = os.getenv("ECFR_CACHE_MAX_ENTRIES") or os.getenv("FR_CACHE_MAX_ENTRIES")
        max_entries = int(max_env) if max_env else 4096
        self.cache = HTTPCache(
            cache_dir or Path(".cache/api/ecfr"),
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
        )
        env_limit = os.getenv("ECFR_MAX_CALLS") or os.getenv("FR_MAX_CALLS")
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
        if self.api_key:
            # Prefer header auth to avoid leaking keys into URLs or logs.
            headers["X-Api-Key"] = self.api_key
        _logger.info("api.request", url=url, params=params, limit=self.request_limit)
        try:
            with budget.consume("ecfr", self.request_limit):
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
            _logger.error(
                "api.invalid_content_type",
                url=resp.url,
                content_type=content_type,
            )
            raise FederalRegisterError(f"Non-JSON response from eCFR at {resp.url}")
        try:
            payload = resp.json()
        except ValueError as exc:  # pragma: no cover
            _logger.error("api.invalid_json", url=url, error=str(exc))
            raise FederalRegisterError("Invalid JSON from eCFR") from exc
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

    @staticmethod
    def _extract_section(term: str) -> str | None:
        raw = str(term or "").strip()
        if not raw:
            return None
        match = re.match(
            r"^(?:15\s*CFR\s*)?(?:§\s*)?(?P<section>\d{3}\.\S+)$",
            raw,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group("section")
        return None

    @staticmethod
    def _extract_part(term: str) -> str | None:
        raw = str(term or "").strip()
        if not raw:
            return None
        match = re.match(
            r"^(?:15\s*CFR\s*)?(?:Part\s*)?(?P<part>\d{3})$",
            raw,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group("part")
        return None

    @staticmethod
    def _ecfr_source_url(section: str) -> str:
        part = (str(section).split(".", 1)[0] or "").strip()
        if part.isdigit():
            return f"https://www.ecfr.gov/current/title-15/part-{part}/section-{section}"
        return "https://www.ecfr.gov/current/title-15"

    def _extract_text_from_payload(self, payload: object) -> str:
        if isinstance(payload, dict):
            for key in (
                "text",
                "content",
                "body_text",
                "body_html",
                "html",
                "content_html",
                "section_text",
            ):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            for container_key in ("result", "section", "data"):
                inner = payload.get(container_key)
                if isinstance(inner, dict):
                    extracted = self._extract_text_from_payload(inner)
                    if extracted:
                        return extracted
            results = payload.get("results")
            if isinstance(results, list) and results:
                extracted = self._extract_text_from_payload(results[0])
                if extracted:
                    return extracted
        elif isinstance(payload, list) and payload:
            extracted = self._extract_text_from_payload(payload[0])
            if extracted:
                return extracted
        return ""

    def get_section_text(self, section: str) -> str:
        section = str(section or "").strip()
        if not section:
            return ""
        part = (section.split(".", 1)[0] or "").strip()
        if not part.isdigit():
            return ""
        url = f"{self.BASE_URL}/title/15/part/{part}/section/{quote(section, safe='().-')}"
        try:
            data = self._get_json(url, params={})
        except (requests.RequestException, FederalRegisterError) as exc:
            _logger.error("api.request_failed", url=url, section=section, error=str(exc))
            return ""
        text_raw = self._extract_text_from_payload(data)
        return self._clean_text(text_raw)

    def get_ear_articles(self, term: str, *, per_page: int = 5) -> List[Dict[str, str]]:
        """Return normalized eCFR records for ``term`` (Title 15 only)."""

        section = self._extract_section(term)
        if section:
            text = self.get_section_text(section)
            if not text:
                return []
            return [
                {
                    "id": section,
                    "title": f"15 CFR {section}",
                    "publication_date": "",
                    "source_url": self._ecfr_source_url(section),
                    "text": text,
                }
            ]

        part = self._extract_part(term)
        if part:
            # Minimal behavior: return the part heading as a pseudo-record when
            # the API does not expose part-level text to the caller.
            return [
                {
                    "id": part,
                    "title": f"15 CFR Part {part}",
                    "publication_date": "",
                    "source_url": f"https://www.ecfr.gov/current/title-15/part-{part}",
                    "text": f"15 CFR Part {part}",
                }
            ]

        url = f"{self.BASE_URL}/search"
        params = {"per_page": str(per_page), "query": term, "title": "15"}
        try:
            data = self._get_json(url, params)
        except (requests.RequestException, FederalRegisterError) as exc:
            _logger.error("api.request_failed", url=url, term=term, error=str(exc))
            return []
        results: List[Dict[str, str]] = []
        for doc in (data.get("results") or []) if isinstance(data, dict) else []:
            doc_id = str(doc.get("id") or doc.get("section") or doc.get("citation") or "")
            text_raw = self._extract_text_from_payload(doc)
            text = self._clean_text(text_raw)
            if not text:
                continue
            results.append(
                {
                    "id": doc_id,
                    "title": str(doc.get("title") or doc.get("citation") or ""),
                    "publication_date": str(doc.get("publication_date") or ""),
                    "source_url": str(doc.get("url") or doc.get("source_url") or ""),
                    "text": text,
                }
            )
        return results

    def get_article_text(self, doc_id: str) -> str:
        """Return cleaned text for an eCFR section (doc_id is the section id)."""

        return self.get_section_text(doc_id)

    # Backwards compatible wrappers
    def search_documents(
        self,
        query: str,
        per_page: int = 100,
        page: int | None = None,
    ) -> List[Dict]:
        url = f"{self.BASE_URL}/search"
        params = {"query": query, "per_page": str(per_page), "title": "15"}
        if page is not None:
            params["page"] = str(page)
        try:
            data = self._get_json(url, params)
        except (requests.RequestException, FederalRegisterError) as exc:
            _logger.error(
                "api.request_failed", url=url, query=query, page=page, error=str(exc)
            )
            return []
        return data.get("results", []) if isinstance(data, dict) else []

    def get_document(self, doc_number: str):
        section = self._extract_section(doc_number) or str(doc_number or "").strip()
        if not section:
            return {}
        part = (section.split(".", 1)[0] or "").strip()
        if not part.isdigit():
            return {}
        url = f"{self.BASE_URL}/title/15/part/{part}/section/{quote(section, safe='().-')}"
        try:
            return self._get_json(url, params={})
        except (requests.RequestException, FederalRegisterError) as exc:
            _logger.error(
                "api.request_failed", url=url, document=doc_number, error=str(exc)
            )
            return {}

    def get_ear_text(self, citation: str) -> str:
        return self.get_section_text(citation)

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
