"""Federal Register API client for EAR text retrieval.

Store FEDREGISTER_API_KEY in Windows Credential Store or vault—never in source.
"""

from __future__ import annotations

import time
from typing import Iterator

import requests
import win32cred


class FederalRegisterError(Exception):
    """Raised for Federal Register client errors or invalid responses."""


class FederalRegisterClient:
    """Simple client for the Federal Register API."""

    BASE_URL = "https://api.federalregister.gov/v1"

    def __init__(self) -> None:
        self.api_key = self._load_api_key()
        self.session = requests.Session()

    @staticmethod
    def _load_api_key() -> str:
        """Load the API key from Windows Credential Manager."""
        try:
            cred = win32cred.CredRead(
                "FEDREGISTER_API_KEY",
                win32cred.CRED_TYPE_GENERIC,
                0,
            )
            return cred["CredentialBlob"].decode("utf-16")
        except Exception as exc:  # pragma: no cover - platform specific
            raise RuntimeError(
                "FEDREGISTER_API_KEY not found in Windows Credential Manager"
            ) from exc

    def _get_json(self, url: str, params: dict) -> dict:
        """Send GET request with retry and return parsed JSON."""
        attempts = 3
        for attempt in range(attempts):
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    raise FederalRegisterError(
                        "Invalid JSON from Federal Register"
                    ) from exc
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", 0)
                if 500 <= status < 600 and attempt < attempts - 1:
                    time.sleep(2 ** attempt)
                    continue
                if 400 <= status < 500:
                    message = getattr(exc.response, "text", str(status))
                    raise FederalRegisterError(
                        f"Federal Register client error: {message}"
                    ) from exc
                raise FederalRegisterError(
                    f"Federal Register request failed: {status}"
                ) from exc
            except requests.RequestException as exc:
                if attempt < attempts - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise FederalRegisterError(
                    f"Federal Register request error: {exc}"
                ) from exc
        raise FederalRegisterError("Federal Register request failed after retries")

    def search_documents(self, query: str, per_page: int = 100) -> Iterator[dict]:
        """Search for documents matching ``query``.

        Parameters
        ----------
        query:
            Free text search query for EAR documents.
        per_page:
            Number of documents to return per page.
        """
        url = f"{self.BASE_URL}/documents"
        page = 1
        while True:
            params = {
                "conditions[any]": query,
                "per_page": per_page,
                "page": page,
                "api_key": self.api_key,
            }
            data = self._get_json(url, params)
            documents = data.get("results", [])
            if not isinstance(documents, list):
                raise FederalRegisterError(
                    "Invalid JSON structure from Federal Register"
                )
            for doc in documents:
                yield doc
            if len(documents) < per_page:
                break
            page += 1

    def get_document(self, doc_number: str) -> dict:
        """Fetch a document by its ``document_number``."""
        url = f"{self.BASE_URL}/documents/{doc_number}"
        params = {"api_key": self.api_key}
        data = self._get_json(url, params)
        if not isinstance(data, dict):
            raise FederalRegisterError(
                "Invalid JSON structure from Federal Register"
            )
        return data
