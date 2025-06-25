"""Client for the Federal Register API."""

from __future__ import annotations

import requests


class FederalRegisterClient:
    """Simple Federal Register API client."""

    BASE_URL = "https://www.federalregister.gov/api/v1"

    def __init__(self) -> None:
        self.session = requests.Session()

    def list_documents(self, params: dict) -> dict:
        """Return documents from the Federal Register."""
        url = f"{self.BASE_URL}/documents.json"
        attempts = 3
        for attempt in range(attempts):
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", 0)
                if 500 <= status < 600 and attempt < attempts - 1:
                    continue
                raise RuntimeError(f"Failed to fetch documents: {exc}") from exc
            except requests.RequestException as exc:
                raise RuntimeError(f"Failed to fetch documents: {exc}") from exc
