from __future__ import annotations

"""Helpers for managing a local Apache Jena installation."""

from pathlib import Path
import json
import os
import shutil
import zipfile
import urllib.request
from urllib.error import HTTPError


def get_jena_home(root: Path = Path(".")) -> Path:
    """Return the repository-scoped Jena home directory."""
    return root / "tools" / "jena"



def _script_dir(jena_home: Path) -> str:
    """Return the subdirectory containing executables."""

    return "bat" if (jena_home / "bat").exists() else "bin"


def _tdb_script(jena_home: Path, *names: str) -> Path:
    """Return the first existing TDB2 script from ``names``."""

    script_dir = _script_dir(jena_home)
    for name in names:
        candidate = jena_home / script_dir / name
        if candidate.exists():
            return candidate
    return jena_home / script_dir / names[0]


def _load_versions(root: Path) -> dict[str, str]:
    """Load version pins from ``tools/versions.json``."""

    version_file = root / "tools" / "versions.json"
    try:
        return json.loads(version_file.read_text())
    except Exception:  # pragma: no cover - file missing or invalid
        return {}


def _expected_scripts(jena_home: Path) -> list[tuple[str, ...]]:
    return [
        ("riot.bat",),
        ("arq.bat",),
        ("tdb2_tdbloader.bat", "tdb2.tdbloader.bat"),
        ("tdb2_tdbquery.bat", "tdb2.tdbquery.bat"),
    ]


def _valid_install(jena_home: Path) -> bool:
    bat = jena_home / "bat"
    if not bat.is_dir():
        return False
    for names in _expected_scripts(jena_home):
        if not any((bat / n).is_file() for n in names):
            return False
    return True


def ensure_jena(download: bool = True, version: str | None = None) -> Path:
    """Ensure Apache Jena exists under ``tools/jena``.

    The default version comes from ``JENA_VERSION`` or ``tools/versions.json``
    and falls back to ``5.3.0``. Downloads prefer the Apache archive and only
    fall back to the live mirror when necessary. The extracted distribution is
    validated to contain Windows ``bat/`` scripts.
    """

    root = Path(".").resolve()
    versions = _load_versions(root)
    version = version or os.getenv("JENA_VERSION") or versions.get("jena", "5.3.0")
    jena_home = get_jena_home(root)

    if _valid_install(jena_home):
        return jena_home
    if jena_home.exists():
        shutil.rmtree(jena_home)
    if not download:
        raise RuntimeError("Apache Jena not installed and download disabled")

    download_dir = root / "tools" / "jena-download"
    download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = download_dir / f"jena-{version}.zip"
    archive_url = f"https://archive.apache.org/dist/jena/binaries/apache-jena-{version}.zip"
    mirror_url = f"https://downloads.apache.org/jena/binaries/apache-jena-{version}.zip"
    attempts = [(archive_url, None), (mirror_url, None)]

    for idx, (url, _) in enumerate(attempts):
        try:
            urllib.request.urlretrieve(url, zip_path)
            attempts[idx] = (url, None)
            break
        except HTTPError as exc:
            attempts[idx] = (url, exc)
            if exc.code != 404 or url == mirror_url:
                break
        except Exception as exc:  # pragma: no cover - network errors
            attempts[idx] = (url, exc)
            break
    else:  # pragma: no cover - all attempts failed
        pass

    if not zip_path.exists():
        details = "; ".join(f"{u}: {e}" for u, e in attempts if e)
        raise RuntimeError(
            f"Failed to download Jena. Attempts: {details}. Set JENA_VERSION to override."
        )

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
        raise RuntimeError(
            "Jena archive missing Windows scripts (expected bat/ with riot.bat, arq.bat, TDB2 loaders/queries)."
        )

    return jena_home


def find_tdbloader() -> Path:
    """Return absolute path to the Jena TDB2 loader."""

    jena_home = get_jena_home(Path(".").resolve())
    return _tdb_script(jena_home, "tdb2_tdbloader.bat", "tdb2.tdbloader.bat").resolve()


def find_tdbquery() -> Path:
    """Return absolute path to the Jena TDB2 query script."""

    jena_home = get_jena_home(Path(".").resolve())
    return _tdb_script(jena_home, "tdb2_tdbquery.bat", "tdb2.tdbquery.bat").resolve()

