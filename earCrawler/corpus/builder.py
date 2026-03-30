from __future__ import annotations

"""Corpus builder with provenance, redaction and snapshot helpers."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlparse

from api_clients.federalregister_client import FederalRegisterClient
from api_clients.upstream_status import UpstreamStatus
from earCrawler.core.ear_crawler import EARCrawler
from earCrawler.core.ear_loader import EARLoader
from earCrawler.core.nsf_case_parser import NSFCaseParser
from earCrawler.core.nsf_loader import NSFLoader
from earCrawler.corpus.artifacts import (
    read_records,
    snapshot_corpus_files,
    write_manifest,
    write_records,
)
from earCrawler.corpus.identity import (
    build_record_id,
    compute_content_sha256,
    content_sha256_for_record,
    normalize_corpus_record,
)
from earCrawler.corpus.metadata import EarMetadataResolver, NSFMetadataResolver
from earCrawler.corpus.records import RecordNormalizer, merge_records
from earCrawler.corpus.sources import (
    EAR_QUERY,
    case_entities_map,
    nsf_entities_for_paragraph,
    read_ear_paragraphs,
    read_nsf_cases_and_paragraphs,
)
from earCrawler.utils.log_json import JsonLogger

SUPPORTED_SOURCES = ("ear", "nsf")
_logger = JsonLogger("corpus")


def _now() -> datetime:
    epoch = os.getenv("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc).replace(
                microsecond=0
            )
        except (TypeError, ValueError, OSError):
            pass
    return datetime.now(timezone.utc).replace(microsecond=0)


class CorpusBuilder:
    def __init__(
        self,
        out_dir: Path,
        live: bool,
        fixtures: Path | None,
        *,
        fr_client_cls=None,
        ear_crawler_cls=None,
        ear_loader_cls=None,
        nsf_parser_cls=None,
        nsf_loader_cls=None,
    ) -> None:
        self.out_dir = out_dir
        self.live = live
        self.fixtures = fixtures
        self.normalizer = RecordNormalizer()
        self._upstream_status: dict[tuple[str, str], dict[str, object]] = {}

        # Preserve monkeypatch behavior in tests by resolving defaults at runtime.
        self._fr_client_cls = fr_client_cls or FederalRegisterClient
        self._ear_crawler_cls = ear_crawler_cls or EARCrawler
        self._ear_loader_cls = ear_loader_cls or EARLoader
        self._nsf_parser_cls = nsf_parser_cls or NSFCaseParser
        self._nsf_loader_cls = nsf_loader_cls or NSFLoader

        self.ear_meta = EarMetadataResolver(
            self.fixtures,
            allow_network=self.live,
            status_hook=self._capture_upstream_status,
            client_factory=self._make_fr_client,
        )

    def build(self, sources: Sequence[str]) -> dict:
        resolved_sources = self._normalise_sources(sources)
        summary: dict[str, int] = {}

        for source in resolved_sources:
            source_records = (
                self._build_ear_records()
                if source == "ear"
                else self._build_nsf_records()
            )
            records_by_id: dict[str, dict] = {}
            for record in source_records:
                normalized = normalize_corpus_record(record)
                record_id = (
                    str(normalized.get("record_id") or normalized.get("id") or "").strip()
                )
                if not record_id:
                    raise ValueError(
                        f"{source} corpus record is missing a source-aware id"
                    )
                if record_id in records_by_id:
                    records_by_id[record_id] = merge_records(
                        records_by_id[record_id], normalized
                    )
                else:
                    records_by_id[record_id] = normalized
            records = [records_by_id[key] for key in sorted(records_by_id)]
            write_records(self.out_dir / f"{source}_corpus.jsonl", records)
            summary[source] = len(records)

        manifest = write_manifest(
            self.out_dir,
            now_func=_now,
            upstream_status=self._manifest_upstream_status(),
        )
        manifest["summary"] = summary
        return manifest

    def _make_fr_client(self) -> FederalRegisterClient:
        return self._fr_client_cls()

    def _build_ear_records(self) -> list[dict]:
        rows = read_ear_paragraphs(
            live=self.live,
            out_dir=self.out_dir,
            fixtures=self.fixtures,
            status_sink=self._capture_upstream_snapshot,
            query=EAR_QUERY,
            crawler_cls=self._ear_crawler_cls,
            fr_client_cls=self._fr_client_cls,
            loader_cls=self._ear_loader_cls,
        )
        records: list[dict] = []
        for row in rows:
            identifier = str(row["identifier"])
            doc_number = identifier.split(":", 1)[0]
            meta = self.ear_meta.resolve(doc_number)
            record = self.normalizer.make_record(
                "ear",
                identifier,
                row["text"],
                meta,
                extra_entities=None,
            )
            if record:
                records.append(record)
        return records

    def _build_nsf_records(self) -> list[dict]:
        cases, paragraphs, upstream_status = read_nsf_cases_and_paragraphs(
            live=self.live,
            out_dir=self.out_dir,
            fixtures=self.fixtures,
            parser_cls=self._nsf_parser_cls,
            loader_cls=self._nsf_loader_cls,
        )
        self._capture_upstream_snapshot(upstream_status)
        resolver = NSFMetadataResolver(self.fixtures, cases)
        case_entities = case_entities_map(cases, self.normalizer.canonical)
        records: list[dict] = []
        for row in paragraphs:
            identifier = str(row["identifier"])
            case_number = identifier.split(":", 1)[0]
            meta = resolver.resolve(case_number)
            extra_entities = nsf_entities_for_paragraph(
                row["text"],
                case_entities.get(case_number, []),
                self.normalizer.extractor,
            )
            record = self.normalizer.make_record(
                "nsf",
                identifier,
                row["text"],
                meta,
                extra_entities=extra_entities,
            )
            if record:
                records.append(record)
        return records

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

    def _capture_upstream_snapshot(
        self, snapshot: Mapping[str, Mapping[str, object]]
    ) -> None:
        for operation, payload in snapshot.items():
            source = str(payload.get("source") or "")
            state = str(payload.get("state") or "")
            if not source or not state:
                continue
            key = (source, operation)
            self._upstream_status[key] = {
                str(k): v for k, v in payload.items() if v is not None
            }
            if state not in {"ok", "no_results"}:
                _logger.warning(
                    "corpus.upstream.degraded",
                    source=source,
                    operation=operation,
                    state=state,
                    details=self._upstream_status[key],
                )

    def _capture_upstream_status(self, status: UpstreamStatus) -> None:
        payload = status.as_dict()
        key = (str(payload.get("source") or ""), str(payload.get("operation") or ""))
        if not key[0] or not key[1]:
            return
        self._upstream_status[key] = payload
        if status.state not in {"ok", "no_results"}:
            _logger.warning(
                "corpus.upstream.degraded",
                source=key[0],
                operation=key[1],
                state=status.state,
                details=payload,
            )

    def _manifest_upstream_status(self) -> list[dict[str, object]]:
        entries = [self._upstream_status[key] for key in sorted(self._upstream_status)]
        return [dict(entry) for entry in entries]


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
        records = read_records(path)
        for idx, record in enumerate(records, start=1):
            source = record.get("source")
            if source not in SUPPORTED_SOURCES:
                problems.append(f"{path.name}:{idx} invalid source")
            identifier = str(record.get("identifier") or "").strip()
            if not identifier:
                problems.append(f"{path.name}:{idx} missing identifier")
            expected_record_id = build_record_id(source, identifier)
            record_id = str(record.get("record_id") or record.get("id") or "").strip()
            if not record_id:
                problems.append(f"{path.name}:{idx} missing record id")
            elif expected_record_id and record_id != expected_record_id:
                problems.append(f"{path.name}:{idx} non-canonical record id")
            if (
                record.get("record_id")
                and record.get("id")
                and record["record_id"] != record["id"]
            ):
                problems.append(f"{path.name}:{idx} record_id/id mismatch")
            sha = content_sha256_for_record(record)
            if not sha or len(str(sha)) != 64:
                problems.append(f"{path.name}:{idx} missing sha256")
            elif not record.get("content_sha256"):
                problems.append(f"{path.name}:{idx} missing content_sha256")
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
            elif sha and compute_content_sha256(paragraph.strip()) != sha:
                problems.append(f"{path.name}:{idx} sha256 does not match paragraph")
            identifiers = record.get("identifiers")
            if not isinstance(identifiers, list) or not identifiers:
                problems.append(f"{path.name}:{idx} missing identifiers")
    if problems:
        _logger.warning(
            "corpus.validate.failed", data_dir=str(data_dir), issues=len(problems)
        )
    else:
        _logger.info("corpus.validate.ok", data_dir=str(data_dir))
    return problems


def snapshot_corpus(data_dir: Path, out_dir: Path) -> Path:
    data_dir = Path(data_dir)
    out_dir = Path(out_dir)
    _logger.info("corpus.snapshot.start", data_dir=str(data_dir), out_dir=str(out_dir))
    target = snapshot_corpus_files(data_dir=data_dir, out_dir=out_dir, now_func=_now)
    _logger.info("corpus.snapshot.complete", target=str(target))
    return target


__all__ = ["build_corpus", "validate_corpus", "snapshot_corpus"]
