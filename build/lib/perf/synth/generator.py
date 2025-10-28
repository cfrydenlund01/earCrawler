from __future__ import annotations

"""Deterministic synthetic KG generator for performance tests."""

import hashlib
import json
import random
from pathlib import Path

BASE = "http://example.org/node/"
PRED = "http://example.org/p"
TEXT = "http://example.org/text"
PROV = "http://www.w3.org/ns/prov#wasGeneratedBy"
PROC = "http://example.org/proc"

COUNTS = {"S": 10, "M": 100}


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def generate(scale: str, out_dir: Path | None = None, seed: int = 12345) -> dict:
    """Generate TTL and NQ files for ``scale`` into ``out_dir``.

    The output is deterministic for a given ``seed`` and ``scale``.
    Returns a manifest dictionary containing counts and content hashes.
    """
    if scale not in COUNTS:
        raise ValueError(f"unknown scale: {scale}")

    if out_dir is None:
        out_dir = Path(__file__).parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    n = COUNTS[scale]
    rng = random.Random(seed)
    ttl_lines: list[str] = []
    for i in range(n):
        iri = f"<{BASE}{i}>"
        val = rng.randint(0, 9999)
        ttl_lines.append(f"{iri} <{PRED}> \"{val}\" .")
        ttl_lines.append(f"{iri} <{TEXT}> \"EAR node {i}\" .")
        ttl_lines.append(f"{iri} <{PROV}> <{PROC}> .")

    ttl_lines.sort()
    ttl = "\n".join(ttl_lines) + "\n"
    ttl_path = out_dir / f"synthetic_{scale}.ttl"
    ttl_path.write_text(ttl, encoding="utf-8")

    nq_lines = [line + " <http://example.org/graph> ." for line in ttl_lines]
    nq_lines.sort()
    nq = "\n".join(nq_lines) + "\n"
    nq_path = out_dir / f"synthetic_{scale}.nq"
    nq_path.write_text(nq, encoding="utf-8")

    manifest = {
        "seed": seed,
        "scale": scale,
        "nodes": n,
        "triples": len(ttl_lines),
        "hashes": {"ttl": _hash(ttl), "nq": _hash(nq)},
    }

    manifest_path = Path(__file__).parent / "manifest.json"
    existing: dict[str, dict] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - corrupt manifest
            existing = {}
    existing[scale] = manifest
    manifest_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return manifest


__all__ = ["generate", "COUNTS"]
