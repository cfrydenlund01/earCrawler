from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
DIST = ROOT / "dist"
SCHEMA = ROOT / "earCrawler" / "schema" / "ear.ttl"
SHAPES = [
    ROOT / "earCrawler" / "shapes" / "entities.shacl.ttl",
    ROOT / "earCrawler" / "shapes" / "parts.shacl.ttl",
]


def ensure_dirs() -> None:
    DIST.mkdir(exist_ok=True)
