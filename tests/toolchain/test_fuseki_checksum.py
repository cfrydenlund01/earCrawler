import json
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pytest

from earCrawler.utils import fuseki_tools


def _make_fuseki_zip(tmp_path: Path, include_server: bool = True) -> Path:
    root = tmp_path / 'src'
    top = root / 'apache-jena-fuseki-5.3.0'
    top.mkdir(parents=True)
    if include_server:
        (top / 'fuseki-server.bat').write_text('echo fuseki')
        (top / 'fuseki-server').write_text('echo fuseki')
    zip_path = tmp_path / 'fuseki.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for file in top.rglob('*'):
            zf.write(file, file.relative_to(root))
    return zip_path


def test_fuseki_checksum_pass(tmp_path, monkeypatch):
    zip_path = _make_fuseki_zip(tmp_path)
    sha = hashlib.sha512(zip_path.read_bytes()).hexdigest()
    versions = {'fuseki': {'version': '5.3.0', 'sha512': sha}}
    vpath = tmp_path / 'tools'
    vpath.mkdir()
    (vpath / 'versions.json').write_text(json.dumps(versions))

    def fake_urlretrieve(url, dest):
        shutil.copy(zip_path, dest)

    monkeypatch.setattr(urllib.request, 'urlretrieve', fake_urlretrieve)
    monkeypatch.chdir(tmp_path)
    home = fuseki_tools.ensure_fuseki()
    assert (home / 'fuseki-server.bat').exists()


def test_fuseki_checksum_mismatch(tmp_path, monkeypatch):
    zip_path = _make_fuseki_zip(tmp_path)
    bad_sha = '0' * 128
    versions = {'fuseki': {'version': '5.3.0', 'sha512': bad_sha}}
    vpath = tmp_path / 'tools'
    vpath.mkdir()
    (vpath / 'versions.json').write_text(json.dumps(versions))

    def fake_urlretrieve(url, dest):
        shutil.copy(zip_path, dest)

    monkeypatch.setattr(urllib.request, 'urlretrieve', fake_urlretrieve)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError) as exc:
        fuseki_tools.ensure_fuseki()
    assert bad_sha in str(exc.value)


def test_fuseki_missing_script(tmp_path, monkeypatch):
    zip_path = _make_fuseki_zip(tmp_path, include_server=False)
    sha = hashlib.sha512(zip_path.read_bytes()).hexdigest()
    versions = {'fuseki': {'version': '5.3.0', 'sha512': sha}}
    vpath = tmp_path / 'tools'
    vpath.mkdir()
    (vpath / 'versions.json').write_text(json.dumps(versions))

    def fake_urlretrieve(url, dest):
        shutil.copy(zip_path, dest)

    monkeypatch.setattr(urllib.request, 'urlretrieve', fake_urlretrieve)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        fuseki_tools.ensure_fuseki()


def test_fuseki_honors_env_override(tmp_path, monkeypatch):
    home = tmp_path / 'fuseki'
    home.mkdir()
    (home / 'fuseki-server.bat').write_text('echo fuseki')
    (home / 'fuseki-server').write_text('echo fuseki')

    monkeypatch.setenv('FUSEKI_HOME', str(home))
    assert fuseki_tools.ensure_fuseki(download=False) == home
