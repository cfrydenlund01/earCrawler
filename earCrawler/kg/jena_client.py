"""Thin convenience wrapper around :class:`earCrawler.kg.sparql.SPARQLClient`."""
from __future__ import annotations

import os
from typing import Any, Dict

from .sparql import SPARQLClient

DEFAULT_DATASET_URL = "http://localhost:3030/ear"


def _resolve_dataset_url(dataset_url: str | None) -> str:
    """Return the dataset URL taking environment overrides into account."""

    return (
        dataset_url
        or os.getenv("FUSEKI_DATASET_URL")
        or DEFAULT_DATASET_URL
    ).rstrip("/")


class JenaClient:
    """High level helper providing select/update ergonomics for Fuseki."""

    def __init__(self, dataset_url: str | None = None, *, timeout: int = 15) -> None:
        self.dataset_url = _resolve_dataset_url(dataset_url)
        query_endpoint = f"{self.dataset_url}/sparql" if not self.dataset_url.endswith("/sparql") else self.dataset_url
        update_endpoint = f"{self.dataset_url}/update" if not self.dataset_url.endswith("/update") else self.dataset_url
        if query_endpoint.endswith("/update"):
            query_endpoint = query_endpoint[:-7] + "sparql"
        self._client = SPARQLClient(
            endpoint=query_endpoint,
            update_endpoint=update_endpoint,
            timeout=timeout,
        )

    def select(self, query: str) -> Dict[str, Any]:
        """Run a SPARQL SELECT query."""

        return self._client.select(query)

    def ask(self, query: str) -> bool:
        """Run a SPARQL ASK query."""

        return self._client.ask(query)

    def construct(self, query: str) -> str:
        """Run a SPARQL CONSTRUCT query."""

        return self._client.construct(query)

    def update(self, query: str) -> None:
        """Run a SPARQL UPDATE statement."""

        self._client.update(query)


__all__ = ["DEFAULT_DATASET_URL", "JenaClient"]
