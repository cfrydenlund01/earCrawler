from __future__ import annotations

"""Helpers for managing a local Apache Jena installation."""

from pathlib import Path
import os
import shutil
import zipfile
import urllib.request
from urllib.error import HTTPError


def get_jena_home(root: Path = Path(".")) -> Path:
    """Return the repository-scoped Jena home directory."""
    return root / "tools" / "jena"


def _tdbloader_path(jena_home: Path) -> Path:
    if os.name == "nt":
        return jena_home / "bat" / "tdb2.tdbloader.bat"
    return jena_home / "bin" / "tdb2.tdbloader"


def ensure_jena(download: bool = True, version: str | None = None) -> Path:
    """Ensure Apache Jena exists under ``tools/jena``.

    The default version is taken from ``JENA_VERSION`` or falls back to
    ``5.3.0``. The binary archive is fetched from the Apache archive and falls
    back to the live download mirror if the requested version is only available
    there.
    """

    version = version or os.getenv("JENA_VERSION", "5.3.0")
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
    archive_url = (
        f"https://archive.apache.org/dist/jena/binaries/apache-jena-{version}.zip"
    )
    urls = [archive_url]

    try:
        urllib.request.urlretrieve(archive_url, zip_path)
    except HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError(
                f"Failed to download Jena from {archive_url}: {exc}. "
                "Set JENA_VERSION to override."
            ) from exc
        mirror_url = (
            f"https://downloads.apache.org/jena/binaries/apache-jena-{version}.zip"
        )
        urls.append(mirror_url)
        try:
            urllib.request.urlretrieve(mirror_url, zip_path)
        except Exception as exc2:  # pragma: no cover - network errors
            raise RuntimeError(
                "Failed to download Jena from {}. Set JENA_VERSION to override.".format(
                    ", ".join(urls)
                )
            ) from exc2
    except Exception as exc:  # pragma: no cover - network errors
        raise RuntimeError(
            f"Failed to download Jena from {archive_url}: {exc}. "
            "Set JENA_VERSION to override."
        ) from exc

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
    if not (jena_home / "bat" / "tdb2.tdbloader.bat").exists():
        raise RuntimeError("Jena archive missing Windows TDB2 loader script")
    return jena_home


def find_tdbloader() -> Path:
    """Return absolute path to the Jena TDB2 loader."""
    jena_home = get_jena_home(Path(".").resolve())
    return _tdbloader_path(jena_home).resolve()

