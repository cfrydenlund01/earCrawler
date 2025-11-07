from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from earCrawler.corpus import build_corpus, validate_corpus, snapshot_corpus


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_build_corpus_with_fixtures(tmp_path: Path) -> None:
    fixtures = Path("tests/fixtures")
    data_dir = tmp_path / "data"

    manifest = build_corpus(["ear", "nsf"], data_dir, live=False, fixtures=fixtures)
    assert (data_dir / "ear_corpus.jsonl").exists()
    assert (data_dir / "nsf_corpus.jsonl").exists()
    assert (data_dir / "manifest.json").exists()
    assert (data_dir / "checksums.sha256").exists()
    assert manifest["summary"]["ear"] == 4
    assert manifest["summary"]["nsf"] == 1

    ear_records = _read_jsonl(data_dir / "ear_corpus.jsonl")
    nsf_records = _read_jsonl(data_dir / "nsf_corpus.jsonl")
    assert any("[redacted]" in rec["paragraph"] for rec in ear_records), "PII should be redacted"
    assert all("example.com?q" not in rec["paragraph"] for rec in ear_records)
    assert len(nsf_records) == 1, "duplicate NSF paragraph should be removed after dedupe"

    first_run = (data_dir / "ear_corpus.jsonl").read_text(encoding="utf-8")
    second_manifest = build_corpus(["ear", "nsf"], data_dir, live=False, fixtures=fixtures)
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
