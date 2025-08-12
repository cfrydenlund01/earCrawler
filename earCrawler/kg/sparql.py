from __future__ import annotations

"""Minimal SPARQL HTTP client for local Fuseki use."""

from typing import Dict, Any, Literal, Optional
import requests


class SPARQLClient:
    """Tiny wrapper around ``requests`` for talking to Fuseki."""

    def __init__(self, endpoint: str = "http://localhost:3030/ear/sparql", timeout: int = 15):
        self.endpoint = endpoint
        self.session = requests.Session()
        self.timeout = timeout

    def _get(self, query: str, accept: str) -> requests.Response:
        resp = self.session.get(
            self.endpoint,
            params={"query": query},
            headers={"Accept": accept},
            timeout=self.timeout,
        )
        return resp

    def select(self, query: str) -> Dict[str, Any]:
        """Execute a ``SELECT`` query and return parsed JSON."""

        resp = self._get(query, "application/sparql-results+json")
        if resp.status_code != 200:
            raise RuntimeError(f"SPARQL SELECT failed: {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:  # pragma: no cover - invalid server response
            raise RuntimeError("Invalid JSON from SPARQL endpoint") from exc
        return data

    def ask(self, query: str) -> bool:
        """Execute an ``ASK`` query and return the boolean result."""

        data = self.select(query)
        try:
            return bool(data["boolean"])
        except KeyError as exc:  # pragma: no cover
            raise RuntimeError("Missing boolean result") from exc

    def construct(self, query: str) -> str:
        """Execute a ``CONSTRUCT`` query returning N-Triples."""

        resp = self._get(query, "application/n-triples")
        if resp.status_code != 200:
            raise RuntimeError(f"SPARQL CONSTRUCT failed: {resp.status_code}")
        return resp.text
