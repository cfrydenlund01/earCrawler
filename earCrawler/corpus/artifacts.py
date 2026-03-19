from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence


def read_records(path: Path) -> list[dict]:
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


def write_records(path: Path, records: Sequence[dict]) -> None:
    ordered = sorted(
        records,
        key=lambda rec: (
            rec.get("source") or "",
            rec.get("record_id") or rec.get("id") or "",
            rec.get("id") or "",
        ),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    out_dir: Path,
    *,
    now_func: Callable[[], datetime],
    upstream_status: Sequence[Mapping[str, object]] | None = None,
) -> dict:
    manifest = {
        "generated_at": now_func().isoformat().replace("+00:00", "Z"),
        "files": [],
    }
    if upstream_status:
        manifest["upstream_status"] = [dict(item) for item in upstream_status]
    corpus_files = sorted(out_dir.glob("*_corpus.jsonl"))
    for file_path in corpus_files:
        lines = read_records(file_path)
        manifest["files"].append(
            {
                "name": file_path.name,
                "records": len(lines),
                "sha256": file_sha256(file_path),
            }
        )
    manifest_path = out_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2) + "\n")
    checksum_items = [(fp.name, file_sha256(fp)) for fp in corpus_files]
    checksum_items.append(("manifest.json", file_sha256(manifest_path)))
    checksum_lines = (
        "\n".join(f"{sha}  {name}" for name, sha in sorted(checksum_items)) + "\n"
    )
    with (out_dir / "checksums.sha256").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(checksum_lines)
    return manifest


def snapshot_corpus_files(
    *,
    data_dir: Path,
    out_dir: Path,
    now_func: Callable[[], datetime],
) -> Path:
    timestamp = now_func().strftime("%Y%m%dT%H%M%SZ")
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
    return target


__all__ = [
    "file_sha256",
    "read_records",
    "snapshot_corpus_files",
    "write_manifest",
    "write_records",
]
