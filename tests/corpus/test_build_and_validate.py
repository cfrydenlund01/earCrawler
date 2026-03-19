from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from api_clients.upstream_status import UpstreamStatus
from earCrawler.corpus import build_corpus, validate_corpus, snapshot_corpus
from earCrawler.corpus.identity import build_record_id


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_build_corpus_with_fixtures(tmp_path: Path) -> None:
    fixtures = Path("tests/fixtures")
    data_dir = tmp_path / "data"

    manifest = build_corpus(["ear", "nsf"], data_dir, live=False, fixtures=fixtures)
    assert (data_dir / "ear_corpus.jsonl").exists()
    assert (data_dir / "nsf_corpus.jsonl").exists()
    assert (data_dir / "manifest.json").exists()
    assert (data_dir / "checksums.sha256").exists()
    assert manifest["summary"]["ear"] == 4
    assert manifest["summary"]["nsf"] == 2

    ear_records = _read_jsonl(data_dir / "ear_corpus.jsonl")
    nsf_records = _read_jsonl(data_dir / "nsf_corpus.jsonl")
    assert any(
        "[redacted]" in rec["paragraph"] for rec in ear_records
    ), "PII should be redacted"
    assert all("example.com?q" not in rec["paragraph"] for rec in ear_records)
    shared_text = (
        "John Smith of the University of Testing falsified data in grant "
        "R01-ABC123 leading to sanctions."
    )
    ear_shared = [rec for rec in ear_records if rec["paragraph"] == shared_text]
    nsf_shared = [rec for rec in nsf_records if rec["paragraph"] == shared_text]
    assert len(ear_shared) == 1
    assert len(nsf_shared) == 1
    assert ear_shared[0]["content_sha256"] == nsf_shared[0]["content_sha256"]
    assert ear_shared[0]["id"] != nsf_shared[0]["id"]
    assert ear_shared[0]["id"] == build_record_id("ear", "EAR-001:0")
    assert nsf_shared[0]["id"] == build_record_id("nsf", "NSF-001:0")

    first_run = (data_dir / "ear_corpus.jsonl").read_text(encoding="utf-8")
    second_manifest = build_corpus(
        ["ear", "nsf"], data_dir, live=False, fixtures=fixtures
    )
    assert second_manifest["summary"] == manifest["summary"]
    assert first_run == (data_dir / "ear_corpus.jsonl").read_text(encoding="utf-8")
    assert validate_corpus(data_dir) == []


def test_validate_corpus_detects_missing_fields(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    bad = data_dir / "ear_corpus.jsonl"
    bad.write_text(json.dumps({"source": "ear"}) + "\n", encoding="utf-8")
    problems = validate_corpus(data_dir)
    assert problems


def test_snapshot_corpus(tmp_path: Path, monkeypatch) -> None:
    fixtures = Path("tests/fixtures")
    data_dir = tmp_path / "data"
    build_corpus(["ear"], data_dir, live=False, fixtures=fixtures)

    fixed_now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("earCrawler.corpus.builder._now", lambda: fixed_now)
    target = snapshot_corpus(data_dir, tmp_path / "snapshots")
    assert target.name == "20240101T120000Z"
    assert (target / "ear_corpus.jsonl").exists()
    assert (target / "manifest.json").exists()


def test_live_manifest_includes_upstream_status(tmp_path: Path, monkeypatch) -> None:
    class StubCrawler:
        def __init__(self, _client, storage_dir: Path) -> None:
            self.paragraphs_path = Path(storage_dir) / "ear_paragraphs.jsonl"

        def run(self, _query: str) -> None:
            self.paragraphs_path.parent.mkdir(parents=True, exist_ok=True)
            self.paragraphs_path.write_text(
                json.dumps(
                    {
                        "document_number": "DOC-1",
                        "paragraph_index": 0,
                        "text": "Paragraph from upstream source.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

    class StubFederalRegisterClient:
        def __init__(self, *args, **kwargs) -> None:
            self._status = UpstreamStatus(
                source="federalregister",
                operation="get_document",
                state="retry_exhausted",
                message="network offline",
                retry_attempts=3,
            )

        def get_document(self, _doc_number: str) -> dict:
            return {}

        def get_last_status(self, operation: str | None = None):
            if operation in (None, "get_document"):
                return self._status
            return None

    monkeypatch.setattr("earCrawler.corpus.builder.EARCrawler", StubCrawler)
    monkeypatch.setattr(
        "earCrawler.corpus.builder.FederalRegisterClient",
        StubFederalRegisterClient,
    )
    data_dir = tmp_path / "data"
    manifest = build_corpus(["ear"], data_dir, live=True, fixtures=None)
    upstream_status = manifest.get("upstream_status") or []
    assert upstream_status
    assert upstream_status[0]["source"] == "federalregister"
    assert upstream_status[0]["operation"] == "get_document"
    assert upstream_status[0]["state"] == "retry_exhausted"
    on_disk = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["upstream_status"][0]["state"] == "retry_exhausted"
