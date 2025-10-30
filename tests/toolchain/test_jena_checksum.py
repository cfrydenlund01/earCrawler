import json
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pytest

from earCrawler.utils import jena_tools


def _seed_java_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JENA_HOME", raising=False)
    java_home = tmp_path / "fake-java"
    (java_home / "bin").mkdir(parents=True)
    (java_home / "bin" / "java.exe").write_text("")
    monkeypatch.setenv("JAVA_HOME", str(java_home))


def _make_jena_zip(tmp_path: Path, include_riot: bool = True) -> Path:
    root = tmp_path / 'src'
    bat = root / 'apache-jena-5.3.0' / 'bat'
    bat.mkdir(parents=True)
    if include_riot:
        (bat / 'riot.bat').write_text('echo riot')
    (bat / 'tdb2_tdbloader.bat').write_text('echo loader')
    (bat / 'tdb2_tdbquery.bat').write_text('echo query')
    zip_path = tmp_path / 'jena.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for file in bat.rglob('*'):
            zf.write(file, file.relative_to(root))
    return zip_path


def test_jena_checksum_pass(tmp_path, monkeypatch):
    _seed_java_home(tmp_path, monkeypatch)
    zip_path = _make_jena_zip(tmp_path)
    sha = hashlib.sha512(zip_path.read_bytes()).hexdigest()
    versions = {'jena': {'version': '5.3.0', 'sha512': sha}}
    vpath = tmp_path / 'tools'
    vpath.mkdir()
    (vpath / 'versions.json').write_text(json.dumps(versions))

    def fake_urlretrieve(url, dest):
        shutil.copy(zip_path, dest)

    monkeypatch.setattr(urllib.request, 'urlretrieve', fake_urlretrieve)
    monkeypatch.chdir(tmp_path)
    home = jena_tools.ensure_jena()
    assert (home / 'bat' / 'riot.bat').exists()


def test_jena_checksum_mismatch(tmp_path, monkeypatch):
    _seed_java_home(tmp_path, monkeypatch)
    zip_path = _make_jena_zip(tmp_path)
    bad_sha = '0' * 128
    versions = {'jena': {'version': '5.3.0', 'sha512': bad_sha}}
    vpath = tmp_path / 'tools'
    vpath.mkdir()
    (vpath / 'versions.json').write_text(json.dumps(versions))

    def fake_urlretrieve(url, dest):
        shutil.copy(zip_path, dest)

    monkeypatch.setattr(urllib.request, 'urlretrieve', fake_urlretrieve)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError) as exc:
        jena_tools.ensure_jena()
    assert bad_sha in str(exc.value)


def test_jena_missing_script(tmp_path, monkeypatch):
    _seed_java_home(tmp_path, monkeypatch)
    zip_path = _make_jena_zip(tmp_path, include_riot=False)
    sha = hashlib.sha512(zip_path.read_bytes()).hexdigest()
    versions = {'jena': {'version': '5.3.0', 'sha512': sha}}
    vpath = tmp_path / 'tools'
    vpath.mkdir()
    (vpath / 'versions.json').write_text(json.dumps(versions))

    def fake_urlretrieve(url, dest):
        shutil.copy(zip_path, dest)

    monkeypatch.setattr(urllib.request, 'urlretrieve', fake_urlretrieve)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        jena_tools.ensure_jena()
