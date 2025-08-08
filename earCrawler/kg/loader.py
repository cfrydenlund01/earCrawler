from __future__ import annotations

"""Utilities for loading triples into a local Jena TDB2 store."""

from pathlib import Path
import subprocess


def load_tdb(ttl_path: Path, db_dir: Path = Path("db")) -> None:
    """Loads TTL triples into a Jena TDB2 database at db_dir.
    Requires `tdb2.tdbloader` on PATH.
    """
    db_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["tdb2.tdbloader", "--loc", str(db_dir), str(ttl_path)]
    subprocess.check_call(cmd)
