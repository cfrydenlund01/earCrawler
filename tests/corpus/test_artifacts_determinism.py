from __future__ import annotations

from datetime import datetime, timezone

from earCrawler.corpus.artifacts import write_manifest, write_records


def test_write_manifest_and_checksums_are_deterministic(tmp_path) -> None:
    out_dir = tmp_path / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    write_records(
        out_dir / "nsf_corpus.jsonl",
        [
            {
                "id": "nsf:1",
                "record_id": "nsf:1",
                "source": "nsf",
                "paragraph": "nsf paragraph",
            }
        ],
    )
    write_records(
        out_dir / "ear_corpus.jsonl",
        [
            {
                "id": "ear:1",
                "record_id": "ear:1",
                "source": "ear",
                "paragraph": "ear paragraph",
            }
        ],
    )

    fixed_now = datetime(2026, 3, 19, 17, 45, 0, tzinfo=timezone.utc)
    manifest = write_manifest(out_dir, now_func=lambda: fixed_now)
    names = [entry["name"] for entry in manifest["files"]]
    assert names == ["ear_corpus.jsonl", "nsf_corpus.jsonl"]

    checksum_names = [
        line.split("  ", 1)[1]
        for line in (out_dir / "checksums.sha256").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert checksum_names == ["ear_corpus.jsonl", "manifest.json", "nsf_corpus.jsonl"]

    first_manifest = (out_dir / "manifest.json").read_text(encoding="utf-8")
    second_manifest = write_manifest(out_dir, now_func=lambda: fixed_now)
    assert second_manifest == manifest
    assert (out_dir / "manifest.json").read_text(encoding="utf-8") == first_manifest
