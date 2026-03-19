from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.corpus.artifacts import read_records
from earCrawler.core.ear_crawler import EARCrawler
from earCrawler.core.ear_loader import EARLoader
from earCrawler.core.nsf_case_parser import NSFCaseParser
from earCrawler.core.nsf_loader import NSFLoader
from earCrawler.transforms.canonical import CanonicalRegistry
from earCrawler.transforms.mentions import MentionExtractor

DEFAULT_FIXTURES = Path("tests/fixtures")
EAR_QUERY = "export administration regulations"


def read_ear_paragraphs(
    *,
    live: bool,
    out_dir: Path,
    fixtures: Path | None,
    query: str = EAR_QUERY,
    crawler_cls=EARCrawler,
    fr_client_cls=FederalRegisterClient,
    loader_cls=EARLoader,
) -> list[dict[str, str]]:
    if live:
        crawler = crawler_cls(fr_client_cls(), out_dir / ".ear_crawler")
        crawler.run(query)
        path = crawler.paragraphs_path
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        for payload in read_records(path):
            identifier = (
                f"{payload.get('document_number')}:{payload.get('paragraph_index')}"
            )
            rows.append({"identifier": identifier, "text": payload.get("text", "")})
        return rows
    fixtures_dir = fixtures or DEFAULT_FIXTURES
    loader = loader_cls(fr_client_cls(), query=query)
    paragraphs = loader.run(
        fixtures_dir=fixtures_dir, live=False, output_dir=str(out_dir)
    )
    return [{"identifier": rec["identifier"], "text": rec["text"]} for rec in paragraphs]


def read_nsf_cases_and_paragraphs(
    *,
    live: bool,
    out_dir: Path,
    fixtures: Path | None,
    parser_cls=NSFCaseParser,
    loader_cls=NSFLoader,
) -> tuple[list[dict], list[dict[str, str]], Mapping[str, Mapping[str, object]]]:
    parser = parser_cls()
    if live:
        cases = parser.run(fixtures or Path("."), live=True)
        upstream_status = dict(parser.last_upstream_status)
        return cases, paragraphs_from_cases(cases), upstream_status
    fixtures_dir = fixtures or DEFAULT_FIXTURES
    cases = parser.run(fixtures_dir, live=False)
    loader = loader_cls(parser, fixtures_dir)
    paragraphs = loader.run(
        fixtures_dir=fixtures_dir, live=False, output_dir=str(out_dir)
    )
    return cases, paragraphs, {}


def paragraphs_from_cases(cases: Sequence[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case in cases:
        case_number = str(case.get("case_number") or "")
        for idx, para in enumerate(case.get("paragraphs", [])):
            rows.append({"identifier": f"{case_number}:{idx}", "text": para})
    return rows


def case_entities_map(
    cases: Sequence[dict], canonical: CanonicalRegistry
) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for case in cases:
        case_number = str(case.get("case_number") or "")
        entities = [
            canonical.canonical_name(str(val)) for val in case.get("entities", [])
        ]
        mapping[case_number] = [val for val in entities if val]
    return mapping


def classify_entity(name: str) -> str:
    normalized = name.lower()
    if any(
        prefix in name
        for prefix in (
            "R01-",
            "R21-",
            "R03-",
            "U01-",
            "P30-",
            "K99-",
            "F31-",
            "DOD",
            "NSF",
            "DOE",
        )
    ):
        return "GRANT"
    if any(
        token in normalized
        for token in (
            "university",
            "college",
            "institute",
            "laboratory",
            "inc",
            "llc",
            "gmbh",
            "corp",
            "company",
        )
    ):
        return "ORG"
    if len(name.split()) >= 2:
        return "PERSON"
    return "ORG"


def nsf_entities_for_paragraph(
    text: str,
    candidates: Sequence[str],
    extractor: MentionExtractor,
) -> dict[str, list[str]]:
    if not candidates or not text:
        return {}
    mapping = {f"case:{idx}": candidate for idx, candidate in enumerate(candidates)}
    matches = extractor.extract(text, mapping)
    if not matches:
        return {}
    bucketed: dict[str, list[str]] = {}
    for key in matches:
        name = mapping[key]
        bucket = classify_entity(name)
        bucketed.setdefault(bucket, [])
        if name not in bucketed[bucket]:
            bucketed[bucket].append(name)
    for key, values in bucketed.items():
        bucketed[key] = sorted(values)
    return bucketed


__all__ = [
    "DEFAULT_FIXTURES",
    "EAR_QUERY",
    "case_entities_map",
    "classify_entity",
    "nsf_entities_for_paragraph",
    "paragraphs_from_cases",
    "read_ear_paragraphs",
    "read_nsf_cases_and_paragraphs",
]
