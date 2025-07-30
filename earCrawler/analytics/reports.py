"""Analytics module providing aggregate SPARQL reports."""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List
from urllib.error import HTTPError, URLError

from SPARQLWrapper import SPARQLWrapper, JSON
from SPARQLWrapper.SPARQLExceptions import QueryBadFormed


class AnalyticsError(Exception):
    """Raised when SPARQL analytics queries fail."""


class ReportsGenerator:
    """Generate aggregate reports against a SPARQL endpoint.

    The endpoint URL is loaded from the ``SPARQL_ENDPOINT_URL`` environment
    variable. All queries are predefined; callers cannot supply arbitrary
    SPARQL to avoid injection risks.
    """

    def __init__(self) -> None:
        endpoint = os.getenv("SPARQL_ENDPOINT_URL")
        if not endpoint:
            raise RuntimeError(
                "SPARQL_ENDPOINT_URL environment variable not set"
            )
        self._wrapper = SPARQLWrapper(endpoint)
        self._wrapper.setReturnFormat(JSON)
        self.logger = logging.getLogger(__name__)

        # Only run predefined SPARQL queries; do not accept raw queries from
        # untrusted sources.
        # Do not log or expose SPARQL_ENDPOINT_URL.
    def _execute(self, query: str) -> List[dict]:
        """Execute ``query`` and return result bindings.

        Retries transient HTTP errors up to two times using exponential
        backoff. Any persistent failure raises :class:`AnalyticsError`.
        """

        attempts = 3
        delay = 1.0
        for attempt in range(attempts):
            try:
                query_str = query.replace("\n", " ")[:200]
                self.logger.info("Executing SPARQL query: %s", query_str)
                self._wrapper.setQuery(query)
                data = self._wrapper.query().convert()
                bindings = data.get("results", {}).get("bindings", [])
                self.logger.info("SPARQL returned %d rows", len(bindings))
                return bindings
            except HTTPError as exc:
                code = getattr(exc, "code", 0)
                if 500 <= code < 600 and attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise AnalyticsError(
                    f"SPARQL endpoint error: {code}"
                ) from exc
            except URLError as exc:
                if attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise AnalyticsError(
                    f"SPARQL endpoint unreachable: {exc.reason}"
                ) from exc
            except QueryBadFormed as exc:  # pragma: no cover
                raise AnalyticsError("Bad SPARQL query") from exc
            except Exception as exc:  # pragma: no cover - unexpected errors
                if attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise AnalyticsError(
                    f"SPARQL query failed: {exc}"
                ) from exc
        raise AnalyticsError("SPARQL query failed after retries")

    def count_entities_by_country(self) -> Dict[str, int]:
        """Return a mapping of country codes to entity counts."""
        query = (
            "SELECT ?country (COUNT(?entity) AS ?count)\n"
            "WHERE { ?entity <urn:prop:country> ?country }\n"
            "GROUP BY ?country"
        )
        bindings = self._execute(query)
        result: Dict[str, int] = {}
        for b in bindings:
            country = b.get("country", {}).get("value")
            count = b.get("count", {}).get("value")
            if country is not None and count is not None:
                result[str(country)] = int(count)
        return result

    def count_documents_by_year(self) -> Dict[int, int]:
        """Return document counts grouped by publication year."""
        query = (
            "SELECT ?year (COUNT(?doc) AS ?count)\n"
            "WHERE { ?doc <urn:prop:year> ?year }\n"
            "GROUP BY ?year"
        )
        bindings = self._execute(query)
        result: Dict[int, int] = {}
        for b in bindings:
            year = b.get("year", {}).get("value")
            count = b.get("count", {}).get("value")
            if year is not None and count is not None:
                result[int(year)] = int(count)
        return result

    def get_document_count_for_entity(self, entity_id: str) -> int:
        """Return the number of documents linked to ``entity_id``."""
        entity_id_escaped = entity_id.replace('"', '\\"')
        query = (
            "SELECT (COUNT(?doc) AS ?count)\n"
            "WHERE {\n"
            "  ?doc <urn:prop:entity> ?e .\n"
            f'  FILTER (?e = "{entity_id_escaped}")\n'
            "}"
        )
        bindings = self._execute(query)
        if not bindings:
            return 0
        count = bindings[0].get("count", {}).get("value", "0")
        return int(count)
