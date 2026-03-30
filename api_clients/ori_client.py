"""Scaffold client for ORI case listings and details.

The client uses simple GET requests with exponential backoff. Secrets are not
required. Live mode is disabled in tests to avoid network calls.
"""

from __future__ import annotations

import time

import requests

from earCrawler.utils.log_json import JsonLogger
from api_clients.upstream_status import (
    UpstreamResult,
    UpstreamState,
    UpstreamStatus,
    UpstreamStatusTracker,
)


_logger = JsonLogger("ori-client")


class ORIClientError(Exception):
    """Raised for ORI client errors or invalid responses."""

    def __init__(
        self,
        message: str,
        *,
        state: UpstreamState = "upstream_unavailable",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.state = state
        self.status_code = status_code


class ORIClient:
    """Tiny ORI HTTP client."""

    BASE_URL = "https://ori.hhs.gov"
    LISTING_PATHS = (
        "/case_summary",
        "/content/case_summary",
        "/case_findings",
    )

    def __init__(self, *, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self._owns_session = session is None
        self._status = UpstreamStatusTracker("ori")

    def _record_status(
        self,
        operation: str,
        state: UpstreamState,
        *,
        message: str | None = None,
        status_code: int | None = None,
        retry_attempts: int | None = None,
        result_count: int | None = None,
    ) -> UpstreamStatus:
        status = self._status.set(
            operation,
            state,
            message=message,
            status_code=status_code,
            retry_attempts=retry_attempts,
            result_count=result_count,
        )
        log_fn = _logger.warning if status.degraded else _logger.info
        log_fn(
            "api.upstream_state",
            operation=operation,
            state=state,
            status_code=status_code,
            retry_attempts=retry_attempts,
            result_count=result_count,
            message=message,
            url=getattr(self, "_current_url", None),
        )
        return status

    def get_last_status(self, operation: str | None = None) -> UpstreamStatus | None:
        """Return the latest known upstream status for ``operation``."""
        return self._status.get(operation)

    def get_status_snapshot(self) -> dict[str, dict[str, object]]:
        """Return the latest status payload for each tracked operation."""
        return self._status.snapshot()

    def _get(self, url: str, *, operation: str) -> str:
        attempts = 3
        self._current_url = url
        for attempt in range(attempts):
            try:
                resp = self.session.get(url, timeout=10)
                resp.raise_for_status()
                body = resp.text or ""
                if not body.strip():
                    self._record_status(
                        operation,
                        "invalid_response",
                        message="ORI returned an empty response body",
                        status_code=resp.status_code,
                    )
                    raise ORIClientError(
                        "ORI returned an empty response body",
                        state="invalid_response",
                        status_code=resp.status_code,
                    )
                self._record_status(operation, "ok", result_count=1)
                return body
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", 0)
                if 500 <= status < 600 and attempt < attempts - 1:
                    self._record_status(
                        operation,
                        "upstream_unavailable",
                        message=f"ORI HTTP {status}; retrying",
                        status_code=status,
                        retry_attempts=attempt + 1,
                    )
                    time.sleep(2**attempt)
                    continue
                failure_state: UpstreamState = (
                    "retry_exhausted" if 500 <= status < 600 else "upstream_unavailable"
                )
                self._record_status(
                    operation,
                    failure_state,
                    message=f"ORI request failed with HTTP {status}",
                    status_code=status,
                    retry_attempts=attempt + 1,
                )
                raise ORIClientError(
                    f"ORI request failed: {status}",
                    state=failure_state,
                    status_code=status,
                ) from exc
            except requests.RequestException as exc:
                if attempt < attempts - 1:
                    self._record_status(
                        operation,
                        "upstream_unavailable",
                        message=f"ORI request error; retrying: {exc}",
                        retry_attempts=attempt + 1,
                    )
                    time.sleep(2**attempt)
                    continue
                self._record_status(
                    operation,
                    "retry_exhausted",
                    message=f"ORI request error after retries: {exc}",
                    retry_attempts=attempt + 1,
                )
                raise ORIClientError(
                    f"ORI request error: {exc}",
                    state="retry_exhausted",
                ) from exc
        self._record_status(
            operation,
            "retry_exhausted",
            message="ORI request failed after retries",
            retry_attempts=attempts,
        )
        raise ORIClientError(
            "ORI request failed after retries",
            state="retry_exhausted",
        )

    def get_listing_html(self) -> str:
        """Return HTML for the case findings listing page."""
        last_not_found: ORIClientError | None = None
        for path in self.LISTING_PATHS:
            url = f"{self.BASE_URL}{path}"
            try:
                return self._get(url, operation="get_listing_html")
            except ORIClientError as exc:
                if exc.status_code == 404:
                    last_not_found = exc
                    continue
                raise
        if last_not_found is not None:
            raise last_not_found
        raise ORIClientError(
            "ORI listing request failed without an HTTP response",
            state="retry_exhausted",
        )

    def get_listing_html_result(self) -> UpstreamResult[str]:
        """Return listing HTML with explicit upstream status."""
        operation = "get_listing_html"
        try:
            data = self.get_listing_html()
        except ORIClientError:
            status = self.get_last_status(operation) or self._record_status(
                operation,
                "retry_exhausted",
                message="ORI listing request failed without status",
            )
            return UpstreamResult(data="", status=status)
        status = self.get_last_status(operation) or self._record_status(
            operation,
            "ok",
            result_count=1,
        )
        return UpstreamResult(data=data, status=status)

    def get_case_html(self, url: str) -> str:
        """Return HTML for a specific case detail page ``url``."""
        return self._get(url, operation="get_case_html")

    def get_case_html_result(self, url: str) -> UpstreamResult[str]:
        """Return case HTML with explicit upstream status."""
        operation = "get_case_html"
        try:
            data = self.get_case_html(url)
        except ORIClientError:
            status = self.get_last_status(operation) or self._record_status(
                operation,
                "retry_exhausted",
                message="ORI case request failed without status",
            )
            return UpstreamResult(data="", status=status)
        status = self.get_last_status(operation) or self._record_status(
            operation,
            "ok",
            result_count=1,
        )
        return UpstreamResult(data=data, status=status)

    def close(self) -> None:
        try:
            if self._owns_session:
                self.session.close()
        except Exception:
            pass
