"""Typed client for the EarCrawler public API facade."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class EarApiError(RuntimeError):
    """Raised when the API facade returns an error response."""


@dataclass(slots=True)
class EarCrawlerApiClient:
    """Convenience wrapper around the FastAPI facade.

    Parameters
    ----------
    base_url:
        Root URL for the API facade (e.g. ``http://localhost:9001``).
    api_key:
        Optional API key value for authenticated requests.
    session:
        Optional :class:`requests.Session` for connection pooling.
    timeout:
        Request timeout in seconds (defaults to 10).
    """

    base_url: str
    api_key: Optional[str] = None
    session: Optional[requests.Session] = None
    timeout: float = 10.0

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()

    # ------------------------------------------------------------------#
    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = self._session.request(method, url, params=params, headers=headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise EarApiError(f"{resp.status_code}: {resp.text}")
        if resp.headers.get("Content-Type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    # ------------------------------------------------------------------#
    def health(self) -> Dict[str, Any]:
        """Return ``/health`` response."""
        return self._request("GET", "/health")

    def search_entities(self, query: str, *, limit: int = 10) -> Dict[str, Any]:
        """Call ``/v1/search`` with query parameters."""
        params = {"q": query, "limit": str(limit)}
        return self._request("GET", "/v1/search", params=params)

    def get_entity(self, urn: str) -> Dict[str, Any]:
        """Fetch a single entity via ``/v1/entities/{urn}``."""
        return self._request("GET", f"/v1/entities/{urn}")


__all__ = ["EarCrawlerApiClient", "EarApiError"]
