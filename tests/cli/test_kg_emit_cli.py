from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import run


def _write(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def test_cli_kg_emit(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write(data_dir / "ear_corpus.jsonl", [{"id": 1, "sha256": "a" * 64}])
    _write(data_dir / "nsf_corpus.jsonl", [{"id": 1, "sha256": "b" * 64}])
    out_dir = tmp_path / "out"

    cmd = [
        sys.executable,
        "-m",
        "earCrawler.cli",
        "kg-emit",
        "-s",
        "ear",
        "-s",
        "nsf",
        "-i",
        str(data_dir),
        "-o",
        str(out_dir),
    ]
    res = run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert (out_dir / "ear.ttl").exists()
    assert (out_dir / "nsf.ttl").exists()

    bad = run(
        [
            sys.executable,
            "-m",
            "earCrawler.cli",
            "kg-emit",
            "-s",
            "bogus",
            "-i",
            str(data_dir),
            "-o",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0
