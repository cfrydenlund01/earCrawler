from __future__ import annotations

"""Helpers for managing a local Apache Jena installation."""

from pathlib import Path
import os
import shutil
import zipfile
import urllib.request


def get_jena_home(root: Path = Path(".")) -> Path:
    """Return the repository-scoped Jena home directory."""
    return root / "tools" / "jena"


def _tdbloader_path(jena_home: Path) -> Path:
    if os.name == "nt":
        return jena_home / "bat" / "tdb2.tdbloader.bat"
    return jena_home / "bin" / "tdb2.tdbloader"


def ensure_jena(download: bool = True, version: str = "4.10.0") -> Path:
    """Ensure Apache Jena exists under tools/jena.

    If the TDB2 loader is missing and ``download`` is True, the archive is
    retrieved and extracted into the tools directory.
    """

    root = Path(".").resolve()
    jena_home = get_jena_home(root)
    loader = _tdbloader_path(jena_home)
    if loader.exists():
        return jena_home
    if not download:
        raise RuntimeError("Apache Jena not installed and download disabled")

    download_dir = root / "tools" / "jena-download"
    download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = download_dir / f"jena-{version}.zip"
    url = (
        f"https://downloads.apache.org/jena/binaries/apache-jena-{version}.zip"
    )
    try:
        urllib.request.urlretrieve(url, zip_path)
    except Exception as exc:  # pragma: no cover - network errors
        raise RuntimeError(f"Failed to download Jena: {exc}") from exc

    if zip_path.stat().st_size < 5 * 1024 * 1024:
        raise RuntimeError("Downloaded Jena archive is too small")

    temp_dir = root / "tools" / "jena-temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(temp_dir)
    extracted = temp_dir / f"apache-jena-{version}"
    if not extracted.exists():
        raise RuntimeError("Downloaded Jena archive missing expected folder")
    if jena_home.exists():
        shutil.rmtree(jena_home)
    shutil.move(str(extracted), jena_home)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return jena_home


def find_tdbloader() -> Path:
    """Return absolute path to the Jena TDB2 loader."""
    jena_home = get_jena_home(Path(".").resolve())
    return _tdbloader_path(jena_home).resolve()

