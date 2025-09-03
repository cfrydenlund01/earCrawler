from __future__ import annotations
"""Helpers for managing a local Apache Jena installation with checksum verification."""

from pathlib import Path
import hashlib
import json
import os
import shutil
import urllib.request
import zipfile
from urllib.error import HTTPError


def get_jena_home(root: Path = Path(".")) -> Path:
    """Return the repository-scoped Jena home directory."""
    return root / "tools" / "jena"


def _load_versions(root: Path) -> dict:
    version_file = root / "tools" / "versions.json"
    try:
        return json.loads(version_file.read_text())
    except Exception:  # pragma: no cover - missing or invalid
        return {}


def _expected_scripts(jena_home: Path) -> list[list[str]]:
    return [
        ["riot.bat"],
        ["tdb2_tdbloader.bat", "tdb2.tdbloader.bat"],
        ["tdb2_tdbquery.bat", "tdb2.tdbquery.bat"],
    ]


def _valid_install(jena_home: Path) -> bool:
    bat = jena_home / "bat"
    if not bat.is_dir():
        return False
    for names in _expected_scripts(jena_home):
        if not any((bat / n).is_file() for n in names):
            return False
    return True


def _verify_sha512(path: Path, expected: str) -> None:
    h = hashlib.sha512()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError(f"Jena SHA512 mismatch: expected {expected}, got {actual}")


def ensure_jena(download: bool = True, version: str | None = None) -> Path:
    """Ensure Apache Jena exists under ``tools/jena`` with checksum verification."""
    root = Path(".").resolve()
    versions = _load_versions(root)
    jena_info = versions.get("jena", {})
    version = version or os.getenv("JENA_VERSION") or jena_info.get("version", "5.3.0")
    expected_hash = jena_info.get("sha512")
    jena_home = get_jena_home(root)

    if _valid_install(jena_home):
        return jena_home
    if jena_home.exists():
        shutil.rmtree(jena_home)
    if not download:
        raise RuntimeError("Apache Jena not installed and download disabled")

    download_dir = root / "tools" / "jena-download"
    download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = download_dir / f"apache-jena-{version}.zip"
    archive_url = f"https://archive.apache.org/dist/jena/binaries/apache-jena-{version}.zip"
    mirror_url = f"https://downloads.apache.org/jena/binaries/apache-jena-{version}.zip"
    attempts = [archive_url, mirror_url]
    for url in attempts:
        try:
            urllib.request.urlretrieve(url, zip_path)
            break
        except HTTPError as exc:
            if exc.code == 404 and url != mirror_url:
                continue
            raise

    if expected_hash:
        _verify_sha512(zip_path, expected_hash)

    temp_dir = root / "tools" / "jena-temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(temp_dir)
    extracted = temp_dir / f"apache-jena-{version}"
    if not extracted.exists():
        raise RuntimeError("Downloaded Jena archive missing expected folder")
    shutil.move(str(extracted), jena_home)
    shutil.rmtree(temp_dir, ignore_errors=True)

    if not _valid_install(jena_home):
        raise RuntimeError("Jena archive missing required Windows scripts")
    return jena_home


# Backwards compatible Fuseki helper
from . import fuseki_tools as _fuseki_tools  # noqa: E402

def ensure_fuseki(*args, **kwargs):  # pragma: no cover - simple delegate
    return _fuseki_tools.ensure_fuseki(*args, **kwargs)


def find_tdbloader() -> Path:
    jena_home = get_jena_home(Path(".").resolve())
    for names in _expected_scripts(jena_home)[1:2]:
        for n in names:
            cand = jena_home / "bat" / n
            if cand.exists():
                return cand.resolve()
    return jena_home / "bat" / "tdb2_tdbloader.bat"


def find_tdbquery() -> Path:
    jena_home = get_jena_home(Path(".").resolve())
    for names in _expected_scripts(jena_home)[2:3]:
        for n in names:
            cand = jena_home / "bat" / n
            if cand.exists():
                return cand.resolve()
    return jena_home / "bat" / "tdb2_tdbquery.bat"
