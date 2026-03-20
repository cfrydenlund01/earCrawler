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
from api_clients.upstream_status import (
    UpstreamResult,
    UpstreamState,
    UpstreamStatus,
    UpstreamStatusTracker,
)


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

    def __init__(
        self,
        message: str,
        *,
        state: UpstreamState = "invalid_response",
    ) -> None:
        super().__init__(message)
        self.state = state


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
        self._status = UpstreamStatusTracker("federalregister")
        _logger.info(
            "api.client.init",
            user_agent=self.user_agent,
            request_limit=self.request_limit,
        )

    def _record_status(
        self,
        operation: str,
        state: UpstreamState,
        *,
        message: str | None = None,
        status_code: int | None = None,
        retry_attempts: int | None = None,
        result_count: int | None = None,
        cache_hit: bool | None = None,
        cache_age_seconds: float | None = None,
    ) -> UpstreamStatus:
        status = self._status.set(
            operation,
            state,
            message=message,
            status_code=status_code,
            retry_attempts=retry_attempts,
            result_count=result_count,
            cache_hit=cache_hit,
            cache_age_seconds=cache_age_seconds,
        )
        log_fn = _logger.warning if status.degraded else _logger.info
        log_fn(
            "api.upstream_state",
            operation=operation,
            state=state,
            status_code=status_code,
            retry_attempts=retry_attempts,
            result_count=result_count,
            cache_hit=cache_hit,
            cache_age_seconds=cache_age_seconds,
            message=message,
        )
        return status

    def get_last_status(self, operation: str | None = None) -> UpstreamStatus | None:
        """Return the latest known upstream status for ``operation``."""
        return self._status.get(operation)

    def get_status_snapshot(self) -> dict[str, dict[str, object]]:
        """Return the latest status payload for each tracked operation."""
        return self._status.snapshot()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1),
        retry=retry_if_exception_type(requests.RequestException),
        before_sleep=_log_retry,
    )
    def _get_json(self, url: str, params: dict[str, str]) -> tuple[dict, bool, float | None]:
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
                alt_url = resp.url.replace("https://api.federalregister.gov/v1", alt_host)
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
            cache_age_seconds=getattr(resp, "cache_age_seconds", None),
            result_count=(
                len(payload.get("results", [])) if isinstance(payload, dict) else None
            ),
        )
        return (
            payload,
            bool(getattr(resp, "from_cache", False)),
            (
                float(getattr(resp, "cache_age_seconds"))
                if getattr(resp, "cache_age_seconds", None) is not None
                else None
            ),
        )

    @staticmethod
    def _classify_request_error(exc: requests.RequestException) -> tuple[UpstreamState, int | None]:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code is not None and 400 <= int(status_code) < 500:
            return "upstream_unavailable", int(status_code)
        return "retry_exhausted", int(status_code) if status_code is not None else None

    @staticmethod
    def _normalize_json_result(
        payload: dict | tuple[dict, bool, float | None],
    ) -> tuple[dict, bool, float | None]:
        if isinstance(payload, tuple) and len(payload) == 3:
            data, cache_hit, cache_age_seconds = payload
            return dict(data), bool(cache_hit), (
                float(cache_age_seconds) if cache_age_seconds is not None else None
            )
        return dict(payload), False, None

    def get_ear_articles(self, term: str, *, per_page: int = 5) -> List[Dict[str, str]]:
        """Return normalized EAR article records for ``term``."""
        return self.get_ear_articles_result(term, per_page=per_page).data

    def get_ear_articles_result(
        self, term: str, *, per_page: int = 5
    ) -> UpstreamResult[List[Dict[str, str]]]:
        """Return normalized EAR articles with explicit upstream status."""
        operation = "get_ear_articles"
        url = f"{self.BASE_URL}/documents"
        params = {"per_page": str(per_page), "conditions[term]": term}
        try:
            data, cache_hit, cache_age_seconds = self._normalize_json_result(
                self._get_json(url, params)
            )
        except FederalRegisterError as exc:
            status = self._record_status(operation, exc.state, message=str(exc))
            _logger.error(
                "api.request_failed",
                url=url,
                term=term,
                state=exc.state,
                error=str(exc),
            )
            return UpstreamResult(data=[], status=status)
        except requests.RequestException as exc:
            state, status_code = self._classify_request_error(exc)
            status = self._record_status(
                operation,
                state,
                message=str(exc),
                status_code=status_code,
                retry_attempts=3 if state == "retry_exhausted" else None,
            )
            _logger.error(
                "api.request_failed",
                url=url,
                term=term,
                state=state,
                status_code=status_code,
                error=str(exc),
            )
            return UpstreamResult(data=[], status=status)
        results: List[Dict[str, str]] = []
        for doc in data.get("results", []):
            doc_id = str(doc.get("document_number") or doc.get("id") or "")
            text_raw = doc.get("body_html") or doc.get("body_text") or ""
            if not text_raw and doc_id:
                # List results often omit body text; fetch the detail JSON when needed.
                detail = self.get_document(doc_id) or {}
                text_raw = detail.get("body_html") or detail.get("body_text") or ""
            if not text_raw:
                text_raw = doc.get("abstract") or " ".join(doc.get("excerpts") or []) or ""
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
        if results:
            status = self._record_status(
                operation,
                "ok",
                result_count=len(results),
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        else:
            status = self._record_status(
                operation,
                "no_results",
                message=f"No documents for term={term!r}",
                result_count=0,
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        return UpstreamResult(data=results, status=status)

    def get_article_text(self, doc_id: str) -> str:
        """Return cleaned text for a Federal Register document."""
        return self.get_article_text_result(doc_id).data

    def get_article_text_result(self, doc_id: str) -> UpstreamResult[str]:
        """Return cleaned text with explicit upstream status."""
        operation = "get_article_text"
        url = f"{self.BASE_URL}/documents/{doc_id}"
        try:
            data, cache_hit, cache_age_seconds = self._normalize_json_result(
                self._get_json(url, params={})
            )
        except FederalRegisterError as exc:
            status = self._record_status(operation, exc.state, message=str(exc))
            _logger.error(
                "api.request_failed",
                url=url,
                document=doc_id,
                state=exc.state,
                error=str(exc),
            )
            return UpstreamResult(data="", status=status)
        except requests.RequestException as exc:
            state, status_code = self._classify_request_error(exc)
            status = self._record_status(
                operation,
                state,
                message=str(exc),
                status_code=status_code,
                retry_attempts=3 if state == "retry_exhausted" else None,
            )
            _logger.error(
                "api.request_failed",
                url=url,
                document=doc_id,
                state=state,
                status_code=status_code,
                error=str(exc),
            )
            return UpstreamResult(data="", status=status)
        text = self._clean_text(data.get("body_html") or data.get("body_text") or "")
        if text:
            status = self._record_status(
                operation,
                "ok",
                result_count=1,
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        else:
            status = self._record_status(
                operation,
                "no_results",
                message=f"Document {doc_id!r} has no body text",
                result_count=0,
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        return UpstreamResult(data=text, status=status)

    # Backwards compatible wrappers
    def search_documents(
        self,
        query: str,
        per_page: int = 100,
        page: int | None = None,
    ) -> List[Dict]:
        return self.search_documents_result(query, per_page=per_page, page=page).data

    def search_documents_result(
        self,
        query: str,
        per_page: int = 100,
        page: int | None = None,
    ) -> UpstreamResult[List[Dict]]:
        """Return raw Federal Register documents with explicit upstream status."""
        operation = "search_documents"
        url = f"{self.BASE_URL}/documents"
        params = {"conditions[any]": query, "per_page": str(per_page)}
        if page is not None:
            params["page"] = str(page)
        try:
            data, cache_hit, cache_age_seconds = self._normalize_json_result(
                self._get_json(url, params)
            )
        except FederalRegisterError as exc:
            status = self._record_status(operation, exc.state, message=str(exc))
            _logger.error(
                "api.request_failed",
                url=url,
                query=query,
                page=page,
                state=exc.state,
                error=str(exc),
            )
            return UpstreamResult(data=[], status=status)
        except requests.RequestException as exc:
            state, status_code = self._classify_request_error(exc)
            status = self._record_status(
                operation,
                state,
                message=str(exc),
                status_code=status_code,
                retry_attempts=3 if state == "retry_exhausted" else None,
            )
            _logger.error(
                "api.request_failed",
                url=url,
                query=query,
                page=page,
                state=state,
                status_code=status_code,
                error=str(exc),
            )
            return UpstreamResult(data=[], status=status)
        results = data.get("results", [])
        if results:
            status = self._record_status(
                operation,
                "ok",
                result_count=len(results),
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        else:
            status = self._record_status(
                operation,
                "no_results",
                message=f"No documents for query={query!r}",
                result_count=0,
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        return UpstreamResult(data=list(results), status=status)

    def get_document(self, doc_number: str):
        return self.get_document_result(doc_number).data

    def get_document_result(self, doc_number: str) -> UpstreamResult[dict]:
        """Return one Federal Register document with explicit upstream status."""
        operation = "get_document"
        url = f"{self.BASE_URL}/documents/{doc_number}"
        try:
            data, cache_hit, cache_age_seconds = self._normalize_json_result(
                self._get_json(url, params={})
            )
        except FederalRegisterError as exc:
            status = self._record_status(operation, exc.state, message=str(exc))
            _logger.error(
                "api.request_failed",
                url=url,
                document=doc_number,
                state=exc.state,
                error=str(exc),
            )
            return UpstreamResult(data={}, status=status)
        except requests.RequestException as exc:
            state, status_code = self._classify_request_error(exc)
            status = self._record_status(
                operation,
                state,
                message=str(exc),
                status_code=status_code,
                retry_attempts=3 if state == "retry_exhausted" else None,
            )
            _logger.error(
                "api.request_failed",
                url=url,
                document=doc_number,
                state=state,
                status_code=status_code,
                error=str(exc),
            )
            return UpstreamResult(data={}, status=status)
        if data:
            status = self._record_status(
                operation,
                "ok",
                result_count=1,
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        else:
            status = self._record_status(
                operation,
                "no_results",
                message=f"Document {doc_number!r} not found",
                result_count=0,
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        return UpstreamResult(data=dict(data), status=status)

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
