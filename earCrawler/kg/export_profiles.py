"""Export graphs into multiple profiles (TTL, NT, gz, manifest)."""
from __future__ import annotations

import gzip
import json
import hashlib
from pathlib import Path
from shutil import copyfileobj

import rdflib


def export_profiles(ttl_source: Path, out_dir: Path, *, stem: str = "dataset") -> dict:
    """Produce Turtle, N-Triples, and gzipped variants with checksums."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = rdflib.Graph()
    graph.parse(ttl_source, format="turtle")

    ttl_path = out_dir / f"{stem}.ttl"
    nt_path = out_dir / f"{stem}.nt"
    manifest: dict[str, dict] = {}

    _write_graph(graph, ttl_path, fmt="turtle")
    _write_graph(graph, nt_path, fmt="nt")

    ttl_gz = _gzip_file(ttl_path)
    nt_gz = _gzip_file(nt_path)

    for path in (ttl_path, nt_path, ttl_gz, nt_gz):
        manifest[path.name] = _checksum_entry(path)

    manifest_path = out_dir / "manifest.json"
    checksum_path = out_dir / "checksums.sha256"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    checksum_lines = [f"{entry['sha256']}  {name}" for name, entry in sorted(manifest.items())]
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return manifest


def _gzip_file(path: Path) -> Path:
    gz_path = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as src, gz_path.open("wb") as raw:
        with gzip.GzipFile(filename=gz_path.name, mode="wb", fileobj=raw, mtime=0) as dst:
            copyfileobj(src, dst)
    return gz_path


def _checksum_entry(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _write_graph(graph: rdflib.Graph, path: Path, *, fmt: str) -> None:
    data = graph.serialize(format=fmt, encoding="utf-8")
    if fmt == "nt":
        text = data.decode("utf-8")
        lines = [line for line in text.splitlines() if line.strip()]
        lines.sort()
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        path.write_bytes(data)
