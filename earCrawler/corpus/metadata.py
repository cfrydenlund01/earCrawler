from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlparse

from api_clients.federalregister_client import FederalRegisterClient
from api_clients.upstream_status import UpstreamStatus

DEFAULT_DATE = "1970-01-01"


@dataclass
class DocMeta:
    source_url: str
    date: str
    provider: str
    section: str | None = None


def normalise_date(value: str | None) -> str:
    date_str = (value or DEFAULT_DATE).strip()
    try:
        return datetime.fromisoformat(date_str).date().isoformat()
    except ValueError:
        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
            return date_str
        return DEFAULT_DATE


def normalise_url(value: str | None, fallback: str) -> str:
    url = (value or fallback).strip()
    parsed = urlparse(url)
    if parsed.scheme and (parsed.netloc or parsed.scheme == "file"):
        return url
    return fallback


def extract_section(detail: Mapping[str, object]) -> str | None:
    refs = detail.get("cfr_references") or []
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict):
                citation = ref.get("citation") or ref.get("title")
                if citation:
                    return str(citation)
    return None


def load_fixture_metadata(fixtures_dir: Path | None, stem: str) -> dict[str, dict[str, str]]:
    if not fixtures_dir:
        return {}
    path = fixtures_dir / f"{stem}_metadata.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, str]] = {}
    for key, payload in data.items():
        result[str(key)] = {str(k): str(v) for k, v in payload.items()}
    return result


class EarMetadataResolver:
    def __init__(
        self,
        fixtures_dir: Path | None,
        *,
        allow_network: bool,
        status_hook: Callable[[UpstreamStatus], None] | None = None,
        client_factory: Callable[[], FederalRegisterClient] | None = None,
    ) -> None:
        self._metadata = load_fixture_metadata(fixtures_dir, "ear")
        self._client: FederalRegisterClient | None = None
        self._cache: dict[str, DocMeta] = {}
        self._allow_network = allow_network
        self._status_hook = status_hook
        self._client_factory = client_factory or FederalRegisterClient

    def resolve(self, document_number: str) -> DocMeta:
        key = str(document_number)
        if key in self._cache:
            return self._cache[key]
        if key in self._metadata:
            raw = self._metadata[key]
            source_url = (
                raw.get("source_url")
                or f"https://www.federalregister.gov/documents/{key}"
            )
            provider = raw.get("provider") or "federalregister.gov"
            date = normalise_date(raw.get("date"))
            section = raw.get("section")
            meta = DocMeta(
                source_url=normalise_url(
                    source_url, f"https://www.federalregister.gov/documents/{key}"
                ),
                date=date,
                provider=provider,
                section=str(section) if section else None,
            )
            self._cache[key] = meta
            return meta
        if not self._allow_network:
            meta = DocMeta(
                source_url=f"https://www.federalregister.gov/documents/{key}",
                date=DEFAULT_DATE,
                provider="federalregister.gov",
            )
            self._cache[key] = meta
            return meta
        if self._client is None:
            self._client = self._client_factory()
        detail = self._client.get_document(key)
        status = self._client.get_last_status("get_document")
        if status is not None and self._status_hook is not None:
            self._status_hook(status)
        source_url = (
            detail.get("html_url")
            or detail.get("url")
            or f"https://www.federalregister.gov/documents/{key}"
        )
        provider = urlparse(source_url).netloc or "federalregister.gov"
        date = normalise_date(detail.get("publication_date") or detail.get("effective_on"))
        section = extract_section(detail)
        meta = DocMeta(
            source_url=normalise_url(
                source_url, f"https://www.federalregister.gov/documents/{key}"
            ),
            date=date,
            provider=provider or "federalregister.gov",
            section=section,
        )
        self._cache[key] = meta
        return meta


class NSFMetadataResolver:
    def __init__(self, fixtures_dir: Path | None, cases: Sequence[dict]) -> None:
        overrides = load_fixture_metadata(fixtures_dir, "nsf")
        self._metadata: dict[str, DocMeta] = {}
        for case in cases:
            case_no = str(case.get("case_number") or "")
            raw = overrides.get(case_no, {})
            base_url = (
                raw.get("source_url")
                or case.get("url")
                or f"https://ori.hhs.gov/case/{case_no}"
            )
            provider = (
                raw.get("provider") or urlparse(str(base_url)).netloc or "ori.hhs.gov"
            )
            date = raw.get("date") or case.get("decision_date")
            section = raw.get("section")
            self._metadata[case_no] = DocMeta(
                source_url=normalise_url(
                    str(base_url), f"https://ori.hhs.gov/case/{case_no}"
                ),
                date=normalise_date(date),
                provider=provider,
                section=str(section) if section else None,
            )

    def resolve(self, case_number: str) -> DocMeta:
        key = str(case_number)
        if key not in self._metadata:
            self._metadata[key] = DocMeta(
                source_url=f"https://ori.hhs.gov/case/{key}",
                date=DEFAULT_DATE,
                provider="ori.hhs.gov",
            )
        return self._metadata[key]


__all__ = [
    "DEFAULT_DATE",
    "DocMeta",
    "EarMetadataResolver",
    "NSFMetadataResolver",
    "extract_section",
    "load_fixture_metadata",
    "normalise_date",
    "normalise_url",
]
