from __future__ import annotations

"""Corpus builder with provenance, redaction and snapshot helpers."""

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence
from urllib.parse import urlparse

from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.core.ear_crawler import EARCrawler
from earCrawler.core.ear_loader import EARLoader
from earCrawler.core.nsf_case_parser import NSFCaseParser
from earCrawler.core.nsf_loader import NSFLoader
from earCrawler.policy import load_hints
from earCrawler.privacy import scrub_text
from earCrawler.transforms.canonical import CanonicalRegistry
from earCrawler.transforms.mentions import MentionExtractor
from earCrawler.utils.log_json import JsonLogger

SUPPORTED_SOURCES = ("ear", "nsf")
DEFAULT_FIXTURES = Path("tests/fixtures")
DEFAULT_DATE = "1970-01-01"
EAR_QUERY = "export administration regulations"
_logger = JsonLogger("corpus")


@dataclass
class DocMeta:
    source_url: str
    date: str
    provider: str
    section: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalise_date(value: str | None) -> str:
    date_str = (value or DEFAULT_DATE).strip()
    try:
        return datetime.fromisoformat(date_str).date().isoformat()
    except ValueError:
        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
            return date_str
        return DEFAULT_DATE


def _normalise_url(value: str | None, fallback: str) -> str:
    url = (value or fallback).strip()
    parsed = urlparse(url)
    if parsed.scheme and (parsed.netloc or parsed.scheme == "file"):
        return url
    return fallback


def _load_fixture_metadata(fixtures_dir: Path | None, stem: str) -> dict[str, dict[str, str]]:
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
    def __init__(self, fixtures_dir: Path | None, *, allow_network: bool) -> None:
        self._metadata = _load_fixture_metadata(fixtures_dir, "ear")
        self._client: FederalRegisterClient | None = None
        self._cache: dict[str, DocMeta] = {}
        self._allow_network = allow_network

    def resolve(self, document_number: str) -> DocMeta:
        key = str(document_number)
        if key in self._cache:
            return self._cache[key]
        if key in self._metadata:
            raw = self._metadata[key]
            source_url = raw.get("source_url") or f"https://www.federalregister.gov/documents/{key}"
            provider = raw.get("provider") or "federalregister.gov"
            date = _normalise_date(raw.get("date"))
            section = raw.get("section")
            meta = DocMeta(
                source_url=_normalise_url(source_url, f"https://www.federalregister.gov/documents/{key}"),
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
            self._client = FederalRegisterClient()
        detail = self._client.get_document(key)
        source_url = detail.get("html_url") or detail.get("url") or f"https://www.federalregister.gov/documents/{key}"
        provider = urlparse(source_url).netloc or "federalregister.gov"
        date = _normalise_date(detail.get("publication_date") or detail.get("effective_on"))
        section = _extract_section(detail)
        meta = DocMeta(
            source_url=_normalise_url(source_url, f"https://www.federalregister.gov/documents/{key}"),
            date=date,
            provider=provider or "federalregister.gov",
            section=section,
        )
        self._cache[key] = meta
        return meta


class NSFMetadataResolver:
    def __init__(self, fixtures_dir: Path | None, cases: Sequence[dict]) -> None:
        overrides = _load_fixture_metadata(fixtures_dir, "nsf")
        self._metadata: dict[str, DocMeta] = {}
        for case in cases:
            case_no = str(case.get("case_number") or "")
            raw = overrides.get(case_no, {})
            base_url = raw.get("source_url") or case.get("url") or f"https://ori.hhs.gov/case/{case_no}"
            provider = raw.get("provider") or urlparse(str(base_url)).netloc or "ori.hhs.gov"
            date = raw.get("date") or case.get("decision_date")
            section = raw.get("section")
            self._metadata[case_no] = DocMeta(
                source_url=_normalise_url(str(base_url), f"https://ori.hhs.gov/case/{case_no}"),
                date=_normalise_date(date),
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


class CorpusBuilder:
    def __init__(self, out_dir: Path, live: bool, fixtures: Path | None) -> None:
        self.out_dir = out_dir
        self.live = live
        self.fixtures = fixtures
        self.canonical = CanonicalRegistry()
        self.extractor = MentionExtractor()
        self.hint_entities = self._load_hint_entities()
        self.ear_meta = EarMetadataResolver(self.fixtures, allow_network=self.live)

    def build(self, sources: Sequence[str]) -> dict:
        resolved_sources = self._normalise_sources(sources)
        source_priority = {src: idx for idx, src in enumerate(resolved_sources)}
        global_records: dict[str, dict] = {}
        owners: dict[str, str] = {}

        for source in resolved_sources:
            existing_path = self.out_dir / f"{source}_corpus.jsonl"
            for record in _read_records(existing_path):
                sha = record.get("sha256")
                if not sha:
                    continue
                record.setdefault("source", source)
                if sha not in global_records:
                    global_records[sha] = record
                    owners[sha] = source

        for source in resolved_sources:
            if source == "ear":
                new_records = self._build_ear_records()
            else:
                new_records = self._build_nsf_records()
            for record in new_records:
                sha = record["sha256"]
                if sha in global_records:
                    current_owner = owners[sha]
                    if current_owner == source:
                        global_records[sha] = _merge_records(global_records[sha], record)
                    else:
                        prev_rank = source_priority.get(current_owner, 999)
                        new_rank = source_priority.get(source, 999)
                        if new_rank < prev_rank:
                            global_records[sha] = _merge_records(record, global_records[sha])
                            owners[sha] = source
                    continue
                global_records[sha] = record
                owners[sha] = source

        summary: dict[str, int] = {}
        for source in resolved_sources:
            records = [
                global_records[sha]
                for sha in sorted(global_records.keys())
                if owners.get(sha) == source
            ]
            _write_records(self.out_dir / f"{source}_corpus.jsonl", records)
            summary[source] = len(records)
        manifest = _write_manifest(self.out_dir)
        manifest["summary"] = summary
        return manifest

    def _build_ear_records(self) -> list[dict]:
        rows = self._ear_paragraphs()
        records: list[dict] = []
        for row in rows:
            identifier = str(row["identifier"])
            doc_number = identifier.split(":", 1)[0]
            meta = self.ear_meta.resolve(doc_number)
            record = self._make_record("ear", identifier, row["text"], meta, extra_entities=None)
            if record:
                records.append(record)
        return records

    def _ear_paragraphs(self) -> list[dict[str, str]]:
        if self.live:
            crawler = EARCrawler(FederalRegisterClient(), self.out_dir / ".ear_crawler")
            crawler.run(EAR_QUERY)
            path = crawler.paragraphs_path
            if not path.exists():
                return []
            rows: list[dict[str, str]] = []
            for payload in _read_records(path):
                identifier = f"{payload.get('document_number')}:{payload.get('paragraph_index')}"
                rows.append({"identifier": identifier, "text": payload.get("text", "")})
            return rows
        fixtures = self.fixtures or DEFAULT_FIXTURES
        loader = EARLoader(FederalRegisterClient(), query=EAR_QUERY)
        paragraphs = loader.run(fixtures_dir=fixtures, live=False, output_dir=str(self.out_dir))
        return [{"identifier": rec["identifier"], "text": rec["text"]} for rec in paragraphs]

    def _build_nsf_records(self) -> list[dict]:
        parser = NSFCaseParser()
        if self.live:
            cases = parser.run(self.fixtures or Path("."), live=True)
            paragraphs = _paragraphs_from_cases(cases)
        else:
            fixtures = self.fixtures or DEFAULT_FIXTURES
            cases = parser.run(fixtures, live=False)
            loader = NSFLoader(parser, fixtures)
            paragraphs = loader.run(fixtures_dir=fixtures, live=False, output_dir=str(self.out_dir))
        resolver = NSFMetadataResolver(self.fixtures, cases)
        case_entities = _case_entities_map(cases, self.canonical)
        records: list[dict] = []
        for row in paragraphs:
            identifier = str(row["identifier"])
            case_number = identifier.split(":", 1)[0]
            meta = resolver.resolve(case_number)
            extra_entities = _nsf_entities_for_paragraph(
                row["text"],
                case_entities.get(case_number, []),
                self.extractor,
            )
            record = self._make_record("nsf", identifier, row["text"], meta, extra_entities=extra_entities)
            if record:
                records.append(record)
        return records

    def _make_record(
        self,
        source: str,
        identifier: str,
        text: str,
        meta: DocMeta,
        *,
        extra_entities: Mapping[str, Sequence[str]] | None,
    ) -> dict | None:
        normalized = " ".join((text or "").split())
        paragraph = scrub_text(normalized)
        if not paragraph:
            return None
        sha = _sha256_text(paragraph)
        record = {
            "id": identifier,
            "identifier": identifier,
            "source": source,
            "sha256": sha,
            "paragraph": paragraph,
            "text": paragraph,
            "source_url": meta.source_url,
            "date": meta.date,
            "provider": meta.provider,
            "section": meta.section,
            "identifiers": [identifier],
        }
        entities = self._hint_entities_for_paragraph(paragraph)
        if extra_entities:
            for key, values in extra_entities.items():
                if not values:
                    continue
                bucket = entities.setdefault(key, [])
                for value in values:
                    if value not in bucket:
                        bucket.append(value)
        record["entities"] = {k: sorted(v) for k, v in entities.items() if v}
        return record

    def _hint_entities_for_paragraph(self, paragraph: str) -> dict[str, list[str]]:
        if not self.hint_entities:
            return {}
        matches = self.extractor.extract(paragraph, self.hint_entities)
        if not matches:
            return {}
        names = sorted({self.hint_entities[key] for key in matches})
        return {"PROGRAM": names}

    def _load_hint_entities(self) -> dict[str, str]:
        entities: dict[str, str] = {}
        hints = load_hints()
        for idx, hint in enumerate(hints):
            programs = self.canonical.canonical_programs([hint.program])
            for program in programs:
                entities[f"hint:{idx}:{program.lower()}"] = program
        return entities

    @staticmethod
    def _normalise_sources(sources: Sequence[str]) -> list[str]:
        if not sources:
            sources = SUPPORTED_SOURCES
        resolved = []
        for source in sources:
            if source not in SUPPORTED_SOURCES:
                raise ValueError(f"Unsupported source: {source}")
            if source not in resolved:
                resolved.append(source)
        return resolved


def _paragraphs_from_cases(cases: Sequence[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case in cases:
        case_number = str(case.get("case_number") or "")
        for idx, para in enumerate(case.get("paragraphs", [])):
            rows.append({"identifier": f"{case_number}:{idx}", "text": para})
    return rows


def _case_entities_map(cases: Sequence[dict], canonical: CanonicalRegistry) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for case in cases:
        case_number = str(case.get("case_number") or "")
        entities = [canonical.canonical_name(str(val)) for val in case.get("entities", [])]
        mapping[case_number] = [val for val in entities if val]
    return mapping


def _classify_entity(name: str) -> str:
    normalized = name.lower()
    if any(prefix in name for prefix in ("R01-", "R21-", "R03-", "U01-", "P30-", "K99-", "F31-", "DOD", "NSF", "DOE")):
        return "GRANT"
    if any(token in normalized for token in ("university", "college", "institute", "laboratory", "inc", "llc", "gmbh", "corp", "company")):
        return "ORG"
    if len(name.split()) >= 2:
        return "PERSON"
    return "ORG"


def _nsf_entities_for_paragraph(
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
        bucket = _classify_entity(name)
        bucketed.setdefault(bucket, [])
        if name not in bucketed[bucket]:
            bucketed[bucket].append(name)
    for key, values in bucketed.items():
        bucketed[key] = sorted(values)
    return bucketed


def _extract_section(detail: Mapping[str, object]) -> str | None:
    refs = detail.get("cfr_references") or []
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict):
                citation = ref.get("citation") or ref.get("title")
                if citation:
                    return str(citation)
    return None


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _write_records(path: Path, records: Sequence[dict]) -> None:
    ordered = sorted(
        records,
        key=lambda rec: (rec.get("source") or "", rec.get("sha256") or "", rec.get("id") or ""),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _merge_records(primary: dict, secondary: dict) -> dict:
    merged = dict(primary)
    merged_ids = list({*(primary.get("identifiers") or []), *(secondary.get("identifiers") or [])})
    merged["identifiers"] = sorted(merged_ids)
    for field in ("source_url", "date", "provider", "section", "paragraph", "text"):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    entities: dict[str, set[str]] = {}
    for payload in (primary.get("entities") or {}, secondary.get("entities") or {}):
        for key, values in payload.items():
            entities.setdefault(key, set()).update(values)
    merged["entities"] = {k: sorted(v) for k, v in entities.items() if v}
    return merged


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(out_dir: Path) -> dict:
    manifest = {
        "generated_at": _now().isoformat().replace("+00:00", "Z"),
        "files": [],
    }
    corpus_files = sorted(out_dir.glob("*_corpus.jsonl"))
    for file_path in corpus_files:
        lines = _read_records(file_path)
        manifest["files"].append(
            {
                "name": file_path.name,
                "records": len(lines),
                "sha256": _file_sha256(file_path),
            }
        )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    checksum_items = [(fp.name, _file_sha256(fp)) for fp in corpus_files]
    checksum_items.append(("manifest.json", _file_sha256(manifest_path)))
    checksum_lines = "\n".join(f"{sha}  {name}" for name, sha in sorted(checksum_items)) + "\n"
    (out_dir / "checksums.sha256").write_text(checksum_lines, encoding="utf-8")
    return manifest


def build_corpus(
    sources: Sequence[str],
    out_dir: Path,
    live: bool,
    fixtures: Path | None,
) -> dict:
    out_path = Path(out_dir)
    fixtures_path = Path(fixtures) if fixtures else None
    _logger.info(
        "corpus.build.start",
        sources=list(sources) or list(SUPPORTED_SOURCES),
        out_dir=str(out_path),
        live=live,
        fixtures=str(fixtures_path) if fixtures_path else None,
    )
    builder = CorpusBuilder(out_path, live, fixtures_path)
    manifest = builder.build(sources)
    _logger.info(
        "corpus.build.complete",
        out_dir=str(out_path),
        files=len(manifest.get("files", [])),
        summary=manifest.get("summary"),
        live=live,
    )
    return manifest


def validate_corpus(data_dir: Path) -> list[str]:
    problems: list[str] = []
    data_dir = Path(data_dir)
    _logger.info("corpus.validate.start", data_dir=str(data_dir))
    for path in sorted(data_dir.glob("*_corpus.jsonl")):
        records = _read_records(path)
        for idx, record in enumerate(records, start=1):
            source = record.get("source")
            if source not in SUPPORTED_SOURCES:
                problems.append(f"{path.name}:{idx} invalid source")
            sha = record.get("sha256")
            if not sha or len(str(sha)) != 64:
                problems.append(f"{path.name}:{idx} missing sha256")
            for field in ("source_url", "date", "provider"):
                if not record.get(field):
                    problems.append(f"{path.name}:{idx} missing {field}")
            url = record.get("source_url", "")
            parsed = urlparse(url)
            if not (parsed.scheme and parsed.netloc):
                problems.append(f"{path.name}:{idx} invalid source_url")
            try:
                datetime.fromisoformat(str(record.get("date")))
            except Exception:
                problems.append(f"{path.name}:{idx} invalid date")
            paragraph = record.get("paragraph") or record.get("text", "")
            if not isinstance(paragraph, str) or not paragraph.strip():
                problems.append(f"{path.name}:{idx} empty paragraph")
            identifiers = record.get("identifiers")
            if not isinstance(identifiers, list) or not identifiers:
                problems.append(f"{path.name}:{idx} missing identifiers")
    if problems:
        _logger.warning("corpus.validate.failed", data_dir=str(data_dir), issues=len(problems))
    else:
        _logger.info("corpus.validate.ok", data_dir=str(data_dir))
    return problems


def snapshot_corpus(data_dir: Path, out_dir: Path) -> Path:
    data_dir = Path(data_dir)
    out_dir = Path(out_dir)
    _logger.info("corpus.snapshot.start", data_dir=str(data_dir), out_dir=str(out_dir))
    timestamp = _now().strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / timestamp
    counter = 1
    while target.exists():
        counter += 1
        target = out_dir / f"{timestamp}_{counter:02d}"
    target.mkdir(parents=True, exist_ok=True)
    files = [
        data_dir / "ear_corpus.jsonl",
        data_dir / "nsf_corpus.jsonl",
        data_dir / "manifest.json",
        data_dir / "checksums.sha256",
    ]
    for path in files:
        if path.exists():
            shutil.copy2(path, target / path.name)
    _logger.info("corpus.snapshot.complete", target=str(target))
    return target


__all__ = ["build_corpus", "validate_corpus", "snapshot_corpus"]
