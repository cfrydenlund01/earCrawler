"""Scaffold client for ORI case listings and details.

The client uses simple GET requests with exponential backoff. Secrets are not
required. Live mode is disabled in tests to avoid network calls.
"""

from __future__ import annotations

import time

import requests


class ORIClientError(Exception):
    """Raised for ORI client errors or invalid responses."""


class ORIClient:
    """Tiny ORI HTTP client."""

    BASE_URL = "https://ori.hhs.gov"

    def __init__(self) -> None:
        self.session = requests.Session()
        self._owns_session = True

    def _get(self, url: str) -> str:
        attempts = 3
        for attempt in range(attempts):
            try:
                resp = self.session.get(url, timeout=10)
                resp.raise_for_status()
                return resp.text
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", 0)
                if 500 <= status < 600 and attempt < attempts - 1:
                    time.sleep(2**attempt)
                    continue
                raise ORIClientError(f"ORI request failed: {status}") from exc
            except requests.RequestException as exc:
                if attempt < attempts - 1:
                    time.sleep(2**attempt)
                    continue
                raise ORIClientError(f"ORI request error: {exc}") from exc
        raise ORIClientError("ORI request failed after retries")

    def get_listing_html(self) -> str:
        """Return HTML for the case findings listing page."""
        url = f"{self.BASE_URL}/case_findings"
        return self._get(url)

    def get_case_html(self, url: str) -> str:
        """Return HTML for a specific case detail page ``url``."""
        return self._get(url)

    def close(self) -> None:
        try:
            if self._owns_session:
                self.session.close()
        except Exception:
            pass
