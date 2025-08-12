from __future__ import annotations

import sys
from pathlib import Path
from subprocess import run

from earCrawler.kg.emit_ear import emit_ear
from earCrawler.kg.emit_nsf import emit_nsf

FIXTURES = Path(__file__).parent / "fixtures"


def _copy(src: str, dst: Path) -> None:
    dst.write_text((FIXTURES / src).read_text(), encoding="utf-8")


def _run(args: list[str]):
    return run([sys.executable, "-m", "cli.kg_validate", *args], capture_output=True, text=True)


def test_validate_happy(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    _copy("ear_small.jsonl", in_dir / "ear_corpus.jsonl")
    _copy("nsf_small.jsonl", in_dir / "nsf_corpus.jsonl")
    emit_ear(in_dir, out_dir)
    emit_nsf(in_dir, out_dir)
    res = _run(["--glob", str(out_dir / "*.ttl")])
    assert res.returncode == 0
    assert "shacl" in res.stdout


def test_validate_missing_provenance(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    _copy("bad_ear_missing_prov.jsonl", in_dir / "ear_corpus.jsonl")
    emit_ear(in_dir, out_dir)
    res = _run(["--ttl", str(out_dir / "ear.ttl")])
    assert res.returncode == 1
    assert "missing_provenance" in res.stdout
    assert "False" in res.stdout


def test_validate_orphan_entity(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    _copy("bad_nsf_orphan_entity.jsonl", in_dir / "nsf_corpus.jsonl")
    emit_nsf(in_dir, out_dir)
    ttl = out_dir / "nsf.ttl"
    lines = [ln for ln in ttl.read_text().splitlines() if "ent:Entity" not in ln]
    ttl.write_text("\n".join(lines) + "\n")
    res = _run(["--ttl", str(ttl)])
    assert res.returncode == 1
    assert "entity_mentions_without_type" in res.stdout
    res2 = _run(["--ttl", str(ttl), "--fail-on", "shacl-only"])
    assert res2.returncode == 0
