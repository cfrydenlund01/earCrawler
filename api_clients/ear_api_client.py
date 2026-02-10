"""Typed client for the EarCrawler public API facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

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
        Optional API key value for authenticated requests (``X-Api-Key`` header).
    session:
        Optional :class:`requests.Session` for connection pooling.
    timeout:
        Request timeout in seconds (defaults to 10).
    """

    base_url: str
    api_key: Optional[str] = None
    session: Optional[requests.Session] = None
    timeout: float = 10.0
    _owns_session: bool = field(init=False, repr=False, default=False)
    _session: requests.Session = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._owns_session = self.session is None
        self._session = self.session or requests.Session()

    # ------------------------------------------------------------------#
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Mapping[str, Any]] = None,
        allow_statuses: Optional[set[int]] = None,
    ) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        resp = self._session.request(
            method, url, params=params, json=json, headers=headers, timeout=self.timeout
        )
        allowed = allow_statuses or set()
        if resp.status_code >= 400 and resp.status_code not in allowed:
            raise EarApiError(f"{resp.status_code}: {resp.text}")
        if resp.headers.get("Content-Type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    # ------------------------------------------------------------------#
    def health(self) -> dict[str, Any]:
        """Return ``/health`` response."""
        return self._request("GET", "/health")

    def search_entities(
        self, query: str, *, limit: int = 10, offset: int = 0
    ) -> dict[str, Any]:
        """Call ``/v1/search`` with query parameters."""
        params = {"q": query, "limit": str(limit), "offset": str(offset)}
        return self._request("GET", "/v1/search", params=params)

    def get_entity(self, urn: str) -> dict[str, Any]:
        """Fetch a single entity via ``/v1/entities/{urn}``."""
        return self._request("GET", f"/v1/entities/{urn}")

    def get_lineage(self, urn: str) -> dict[str, Any]:
        """Fetch lineage edges via ``/v1/lineage/{urn}``."""
        return self._request("GET", f"/v1/lineage/{urn}")

    def run_template(
        self, template: str, *, parameters: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        """Execute an allow-listed SPARQL template via ``/v1/sparql``."""
        payload = {"template": template, "parameters": dict(parameters or {})}
        return self._request("POST", "/v1/sparql", json=payload)

    def rag_query(
        self, query: str, *, top_k: int = 3, include_lineage: bool = False
    ) -> dict[str, Any]:
        """Call the ``/v1/rag/query`` endpoint."""
        payload = {
            "query": query,
            "top_k": top_k,
            "include_lineage": include_lineage,
        }
        return self._request("POST", "/v1/rag/query", json=payload)

    def rag_answer(
        self, query: str, *, top_k: int = 3, generate: bool = True
    ) -> dict[str, Any]:
        """Call the ``/v1/rag/answer`` endpoint backed by a remote LLM provider."""
        payload = {
            "query": query,
            "top_k": top_k,
            "include_lineage": False,
            "generate": generate,
        }
        params = {"generate": "1" if generate else "0"}
        # 422 is a structured contract failure (LLM output schema violation) and
        # returns a normal JSON body with output_error details.
        return self._request(
            "POST",
            "/v1/rag/answer",
            params=params,
            json=payload,
            allow_statuses={422},
        )

    # --------------------------------------------------------------#
    # Resource lifecycle
    def close(self) -> None:
        try:
            if self._owns_session:
                self._session.close()
        except Exception:
            pass

    def __enter__(self) -> "EarCrawlerApiClient":  # pragma: no cover - convenience
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - convenience
        self.close()


__all__ = ["EarCrawlerApiClient", "EarApiError"]
