from __future__ import annotations

"""Checksum-verified helper for Apache Jena Fuseki."""

from pathlib import Path
import hashlib
import json
import logging
import os
import shutil
import urllib.request
import zipfile
from urllib.error import HTTPError

logger = logging.getLogger(__name__)


def get_fuseki_home(root: Path = Path(".")) -> Path:
    return root / "tools" / "fuseki"


def _load_versions(root: Path) -> dict:
    version_file = root / "tools" / "versions.json"
    try:
        return json.loads(version_file.read_text())
    except Exception:  # pragma: no cover
        return {}


def _verify_sha512(path: Path, expected: str) -> None:
    h = hashlib.sha512()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError(f"Fuseki SHA512 mismatch: expected {expected}, got {actual}")


def _valid_install(fuseki_home: Path) -> bool:
    exe = fuseki_home / ("fuseki-server.bat" if os.name == "nt" else "fuseki-server")
    return exe.is_file()


def ensure_fuseki(download: bool = True, version: str | None = None) -> Path:
    root = Path(".").resolve()

    env_override = os.getenv("FUSEKI_HOME")
    if env_override:
        env_home = Path(env_override).expanduser()
        if _valid_install(env_home):
            return env_home
        if not download:
            raise RuntimeError(
                "FUSEKI_HOME is set but does not look like a valid Apache Jena Fuseki installation"
            )
        logger.warning(
            "FUSEKI_HOME is set but invalid; falling back to managed download (%s)",
            env_home,
        )

    versions = _load_versions(root)
    info = versions.get("fuseki", {})
    version = version or os.getenv("FUSEKI_VERSION") or info.get("version", "5.3.0")
    expected_hash = info.get("sha512")
    fuseki_home = get_fuseki_home(root)

    if _valid_install(fuseki_home):
        return fuseki_home
    if fuseki_home.exists():
        shutil.rmtree(fuseki_home)
    if not download:
        raise RuntimeError("Fuseki not installed and download disabled")

    download_dir = root / "tools" / "fuseki-download"
    download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = download_dir / f"apache-jena-fuseki-{version}.zip"
    archive_url = f"https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-{version}.zip"
    mirror_url = (
        f"https://downloads.apache.org/jena/binaries/apache-jena-fuseki-{version}.zip"
    )
    for url in [archive_url, mirror_url]:
        try:
            urllib.request.urlretrieve(url, zip_path)
            break
        except HTTPError as exc:
            if exc.code == 404 and url != mirror_url:
                continue
            raise

    if expected_hash:
        _verify_sha512(zip_path, expected_hash)

    temp_dir = root / "tools" / "fuseki-temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(temp_dir)
    extracted = temp_dir / f"apache-jena-fuseki-{version}"
    if not extracted.exists():
        raise RuntimeError("Downloaded Fuseki archive missing expected folder")
    shutil.move(str(extracted), fuseki_home)
    shutil.rmtree(temp_dir, ignore_errors=True)

    if not _valid_install(fuseki_home):
        raise RuntimeError("Fuseki archive missing fuseki-server script")
    return fuseki_home
