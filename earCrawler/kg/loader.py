from __future__ import annotations

"""Utilities for loading triples into a local Jena TDB2 store."""

from pathlib import Path
import os
import shutil
import subprocess

from earCrawler.utils.jena_tools import ensure_jena, find_tdbloader


def load_tdb(
    ttl_path: Path, db_dir: Path = Path("db"), auto_install: bool = True
) -> None:
    """Load TTL triples into a Jena TDB2 database at ``db_dir``.

    Parameters
    ----------
    ttl_path: Path
        Path to Turtle file containing triples.
    db_dir: Path, optional
        Destination directory for the TDB2 database.
    auto_install: bool, optional
        If True, download Apache Jena locally when not already present.
    """

    if not ttl_path.exists():
        raise FileNotFoundError(f"Turtle file not found: {ttl_path}")

    db_dir.mkdir(parents=True, exist_ok=True)

    if auto_install:
        ensure_jena(download=True)
        loader = find_tdbloader()
    else:
        loader = find_tdbloader()
        if not loader.exists():
            names = (
                ["tdb2_tdbloader.bat", "tdb2.tdbloader.bat"]
                if os.name == "nt"
                else ["tdb2.tdbloader", "tdb2_tdbloader"]
            )
            candidate = None
            for name in names:
                candidate = shutil.which(name)
                if candidate:
                    loader = Path(candidate)
                    break
            if not candidate:
                raise RuntimeError(
                    "Apache Jena TDB2 not found. Rerun without --no-auto-install to fetch a local copy."
                )

    loader_path = loader.resolve()
    env = os.environ.copy()
    env.setdefault("JENA_HOME", str(loader_path.parent.parent))
    cmd = [str(loader_path), "--loc", str(db_dir), str(ttl_path)]
    try:
        subprocess.check_call(cmd, shell=False, stderr=subprocess.PIPE, env=env)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - error path
        err = exc.stderr.decode() if exc.stderr else ""
        msg = f"TDB2 loader failed: {exc.returncode}"
        if err:
            msg += f": {err}"
        raise RuntimeError(msg) from exc


def enrich_entities_with_tradegov(records, client=None):
    """Enrich entity ``records`` using the Trade.gov API."""
    from api_clients.tradegov_client import TradeGovClient

    tg = client or TradeGovClient()
    enriched = []
    for rec in records:
        name = rec.get("name") if isinstance(rec, dict) else None
        if not name:
            continue
        info = tg.lookup_entity(name)
        if info:
            enriched.append(info)
    return enriched
