"""NSF case parser for research misconduct case summaries.

This module provides tools to parse case summaries published by the
National Science Foundation (NSF) Office of Inspector General (OIG) or
 the Office of Research Integrity (ORI).  Cases are free‑form
narratives describing research misconduct or export control violations.
For each case, the parser splits the text into paragraphs, computes a
SHA‑256 hash for each paragraph, extracts simple entities (persons,
institutions, grant identifiers), and returns structured records.  A
persistent index of hashes facilitates incremental updates across runs.

The parser does not fetch cases from the internet by default.  Use the
``ORIClient`` to retrieve case summaries when live mode is enabled.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

import requests


@dataclass
class NSFEntity:
    """A simple entity extracted from a case summary.

    Parameters
    ----------
    type: str
        The category of entity, e.g. ``"person"``, ``"institution"`` or ``"grant"``.
    value: str
        The surface form of the entity as it appears in the text.
    """

    type: str
    value: str


@dataclass
class NSFParagraphRecord:
    """Structured representation of a single paragraph from a case summary.

    Parameters
    ----------
    case_id:
        Unique identifier for the case (e.g. the document ID or URL slug).
    paragraph_index:
        Zero‑based index of the paragraph within the case.
    text:
        Normalised paragraph text with collapsed whitespace.
    sha256:
        Hex digest of the SHA‑256 hash of ``text`` encoded as UTF‑8.
    entities:
        A list of extracted :class:`NSFEntity` objects.
    source_url:
        URL from which this case was retrieved.
    timestamp:
        ISO‑0860 UTC timestamp when the paragraph was processed.
    """

    case_id: str
    paragraph_index: int
    text: str
    sha256: str
    entities: List[NSFEntity]
    source_url: str
    timestamp: str


class ORIClient:
    """Simple client for retrieving NSF case summaries from ori.hhs.gov.

    The real implementation may fetch the list of cases and individual
    case HTML pages.  To avoid network access during tests and default
    runs, ``live_mode`` must be explicitly enabled.  When
    ``live_mode=False``, the client returns empty results.
    """

    base_url = "https://ori.hhs.gov"

    def __init__(self, live_mode: bool = False, session: Optional[requests.Session] = None) -> None:
        self.live_mode = live_mode
        self.session = session or requests.Session()

    def list_cases(self, per_page: int = 100) -> Iterable[Dict]:
        """Return metadata for available cases.

        When ``live_mode`` is ``False``, yields an empty list.  In
        live mode, this would fetch paginated case indexes from the
        ORI site.
        """
        if not self.live_mode:
            return []
        # Real implementation omitted; returning empty list.
        return []

    def fetch_case_text(self, case_url: str) -> str:
        """Download and return raw HTML or text for a given case URL.

        Returns an empty string if the client is not in live mode or
        if the request fails.
        """
        if not self.live_mode:
            return ""
        try:
            resp = self.session.get(case_url, timeout=15.0)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # pragma: no cover - network failures are non-deterministic in tests
            logging.getLogger(self.__class__.__name__).warning(
                "Failed to fetch case %s: %s", case_url, exc
            )
            return ""


# Regular expressions for entity extraction
PERSON_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)\b")
INSTITUTION_PATTERN = re.compile(
    r"\b(University\s+[A-Z][\w\s]+|Institute\s+[A-Z][\w\s]+|College\s+[A-Z][\w\s]+)\b",
    re.IGNORECASE,
)
GRANT_PATTERN = re.compile(r"\b[A-Z]{2,}\d{5,}\b")


def extract_entities(text: str) -> List[NSFEntity]:
    """Return a list of simple entities found in ``text``.

    The extraction rules are conservative and primarily look for
    capitalised names (two or more capitalised words), common
    institution patterns (e.g. "University X"), and grant identifiers
    consisting of two or more uppercase letters followed by at least
    five digits.
    """
    entities: List[NSFEntity] = []
    # People names: two or more capitalised words
    for match in PERSON_PATTERN.finditer(text):
        name = match.group(1).strip()
        # Exclude matches that contain institution keywords
        if not re.search(r"University|Institute|College", name):
            entities.append(NSFEntity(type="person", value=name))
    # Institutions
    for match in INSTITUTION_PATTERN.finditer(text):
        entities.append(NSFEntity(type="institution", value=match.group(1).strip()))
    # Grant identifiers
    for match in GRANT_PATTERN.finditer(text):
        entities.append(NSFEntity(type="grant", value=match.group(0).strip()))
    return entities


def parse_paragraphs(case_text: str) -> Iterator[str]:
    """Split ``case_text`` into non‑empty paragraphs.

    Paragraphs are separated by one or more blank lines.  Leading and
    trailing whitespace is stripped from each paragraph.
    """
    for paragraph in re.split(r"\n\s*\n", case_text):
        p = paragraph.strip()
        if p:
            yield p


class NSFCaseParser:
    """Parser orchestrator for NSF case summaries.

    Use :meth:`parse_case` to convert a full case narrative into
    structured paragraph records, each accompanied by extracted entities
    and a SHA‑256 hash.  Records can be persisted to disk via
    :meth:`save_records`.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_case(self, case_id: str, case_text: str, source_url: str) -> List[NSFParagraphRecord]:
        """Parse a single case narrative into paragraph records.

        Parameters
        ----------
        case_id:
            Unique identifier for the case (document number or slug).
        case_text:
            Raw case description.
        source_url:
            URL where the case narrative was retrieved.

        Returns
        -------
        list of :class:`NSFParagraphRecord`
            Structured records for each paragraph.
        """
        records: List[NSFParagraphRecord] = []
        for idx, para in enumerate(parse_paragraphs(case_text)):
            # Normalise whitespace within the paragraph
            normalized = " ".join(para.split())
            sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            ents = extract_entities(normalized)
            timestamp = datetime.utcnow().isoformat(sep="T", timespec="seconds") + "Z"
            records.append(
                NSFParagraphRecord(
                    case_id=case_id,
                    paragraph_index=idx,
                    text=normalized,
                    sha256=sha,
                    entities=ents,
                    source_url=source_url,
                    timestamp=timestamp,
                )
            )
        return records

    def save_records(self, records: List[NSFParagraphRecord], output_dir: Path) -> None:
        """Persist a list of records to disk in JSON Lines and index format.

        Parameters
        ----------
        records:
            List of records returned by :meth:`parse_case`.
        output_dir:
            Directory where output files ``nsf_corpus.jsonl`` and
            ``nsf_index.json`` will be stored.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = output_dir / "nsf_corpus.jsonl"
        index_path = output_dir / "nsf_index.json"
        # Load existing index if present
        index_data: Dict[str, NSFParagraphRecord] = {}
        if index_path.exists():
            try:
                raw = json.loads(index_path.read_text(encoding="utf-8"))
                for sha, rec in raw.items():
                    index_data[sha] = NSFParagraphRecord(**rec)
            except Exception as exc:
                self.logger.warning("Failed to load existing nsf index: %s", exc)
        # Determine new records and update index
        new_records: List[NSFParagraphRecord] = []
        for rec in records:
            if rec.sha256 not in index_data:
                new_records.append(rec)
                index_data[rec.sha256] = rec
        # Append new records to corpus file
        if new_records:
            with jsonl_path.open("a", encoding="utf-8") as f:
                for rec in new_records:
                    f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
            # Write updated index to disk
            serialisable = {sha: asdict(r) for sha, r in index_data.items()}
            index_path.write_text(json.dumps(serialisable, ensure_ascii=False, indent=2), encoding="utf-8")
