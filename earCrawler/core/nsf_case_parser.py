"""NSF/ORI case parser with deterministic entity extraction."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List

from bs4 import BeautifulSoup

from api_clients.ori_client import ORIClient


class NSFCaseParser:
    """Parse ORI case HTML into structured records."""

    GRANT_RE = re.compile(
        r"\b(?:R01|R21|R03|U01|P30|K99|F31|DOD|NSF|DOE)[-\s]?[A-Z0-9-]+"
    )
    ORG_RE = re.compile(
        r"\b(?:University|College|Institute|Laborator(?:y|ies)|Inc\.|LLC|Ltd\.|GmbH|AG|SAS|PLC)"
        r"(?:\s+(?:of|and|for|the|[A-Z][a-z]+)){0,5}"
    )
    PERSON_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+")

    @staticmethod
    def normalize(text: str) -> str:
        """Collapse whitespace and trim."""
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def extract_entities(cls, text: str) -> List[str]:
        """Extract entities using regex heuristics."""
        entities: set[str] = set()
        for match in cls.GRANT_RE.findall(text):
            entities.add(match.strip())
        for match in cls.ORG_RE.findall(text):
            entities.add(cls.normalize(match))
        for match in cls.PERSON_RE.findall(text):
            if cls.ORG_RE.match(match):
                continue
            entities.add(match.strip())
        return sorted(entities)

    @staticmethod
    def hash_text(text: str) -> str:
        """Return SHA-256 hash of ``text``."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def paragraphs(self, html: str) -> List[str]:
        """Return normalized paragraphs with minimum length."""
        soup = BeautifulSoup(html, "lxml")
        paras: List[str] = []
        for p in soup.find_all("p"):
            text = self.normalize(p.get_text(" "))
            if len(text) >= 30:
                paras.append(text)
        return paras

    def parse_from_html(self, html: str, url: str) -> Dict[str, object]:
        """Parse a case detail page HTML."""
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("h1")
        title = self.normalize(title_tag.get_text(" ")) if title_tag else ""
        match = re.search(r"Case Number\s*(\S+)", title)
        case_number = match.group(1) if match else ""
        paragraphs = self.paragraphs(html)
        joined = "\n".join(paragraphs)
        entities = self.extract_entities(joined)
        hash_value = self.hash_text(joined)
        return {
            "case_number": case_number,
            "title": title,
            "url": url,
            "paragraphs": paragraphs,
            "entities": entities,
            "hash": hash_value,
        }

    def run(self, fixtures_dir: Path, live: bool = False) -> List[Dict[str, object]]:
        """Parse listing and return list of cases.

        If ``live`` is ``True`` the ORI site is queried; otherwise HTML fixtures
        in ``fixtures_dir`` are used.
        """
        cases: List[Dict[str, object]] = []
        if live:
            client = ORIClient()
            listing_html = client.get_listing_html()
            listing = BeautifulSoup(listing_html, "lxml")
            links = [a["href"] for a in listing.select("a[href]")]
            for link in links:
                url = link if link.startswith("http") else f"{client.BASE_URL}{link}"
                case_html = client.get_case_html(url)
                cases.append(self.parse_from_html(case_html, url))
        else:
            fixtures_dir = Path(fixtures_dir)
            listing_html = (fixtures_dir / "ori_case_listing.html").read_text(encoding="utf-8")
            listing = BeautifulSoup(listing_html, "lxml")
            links = [a["href"] for a in listing.select("a[href]")]
            for link in links:
                case_path = fixtures_dir / link
                case_html = case_path.read_text(encoding="utf-8")
                cases.append(self.parse_from_html(case_html, case_path.as_posix()))
        return cases
