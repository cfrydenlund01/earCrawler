import os
import urllib.request
import zipfile
from pathlib import Path
import json

import pytest

from earCrawler.utils import jena_tools


@pytest.mark.skipif(os.name != "nt", reason="Windows-only")
def test_ensure_java_home_from_path(tmp_path, monkeypatch):
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.delenv("JENA_HOME", raising=False)
    java_dir = tmp_path / "jdk" / "bin"
    java_dir.mkdir(parents=True)
    fake_java = java_dir / "java.exe"
    fake_java.write_text("")
    original_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{java_dir}{os.pathsep}{original_path}")
    home = jena_tools.ensure_java_home()
    assert home == java_dir.parent
    assert os.environ["JAVA_HOME"] == str(java_dir.parent)
    monkeypatch.setenv("JAVA_HOME", str(home))


def test_ensure_java_home_invalid(monkeypatch, tmp_path):
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.delenv("JENA_HOME", raising=False)
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError) as exc:
        jena_tools.ensure_java_home()
    assert "Java installation" in str(exc.value)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only")
def test_ensure_jena_bootstrap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JENA_VERSION", raising=False)
    monkeypatch.delenv("JENA_HOME", raising=False)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    java_home = tmp_path / "fake-java"
    (java_home / "bin").mkdir(parents=True)
    (java_home / "bin" / "java.exe").write_text("")
    monkeypatch.setenv("JAVA_HOME", str(java_home))

    versions = json.loads((Path(__file__).resolve().parents[1] / "tools/versions.json").read_text())
    def fake_urlretrieve(url, filename):
        with zipfile.ZipFile(filename, "w") as zf:
            base = f"apache-jena-{versions['jena']['version']}/bat"
            zf.writestr(f"{base}/riot.bat", "")
            zf.writestr(f"{base}/arq.bat", "")
            zf.writestr(f"{base}/tdb2_tdbloader.bat", "")
            zf.writestr(f"{base}/tdb2_tdbquery.bat", "")
            zf.writestr("payload.bin", os.urandom(6 * 1024 * 1024))

    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

    jena_home = jena_tools.ensure_jena()
    assert (jena_home / "bat/riot.bat").exists()
    assert (jena_home / "bat/arq.bat").exists()
    assert jena_tools.find_tdbloader().is_file()
    assert jena_tools.find_tdbquery().is_file()

    called: list[str] = []

    def blocker(url, filename):
        called.append(url)
        raise AssertionError("network call")

    monkeypatch.setattr(urllib.request, "urlretrieve", blocker)
    assert jena_tools.ensure_jena() == jena_home
    assert not called


@pytest.mark.skipif(os.name != "nt", reason="Windows-only")
def test_ensure_jena_missing_scripts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JENA_HOME", raising=False)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    java_home = tmp_path / "fake-java"
    (java_home / "bin").mkdir(parents=True)
    (java_home / "bin" / "java.exe").write_text("")
    monkeypatch.setenv("JAVA_HOME", str(java_home))

    versions = json.loads((Path(__file__).resolve().parents[1] / "tools/versions.json").read_text())
    def fake_urlretrieve(url, filename):
        with zipfile.ZipFile(filename, "w") as zf:
            zf.writestr(f"apache-jena-{versions['jena']['version']}/README.txt", "")

    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

    with pytest.raises(RuntimeError) as exc:
        jena_tools.ensure_jena()
    assert "Windows scripts" in str(exc.value)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only")
def test_ensure_jena_honors_env_override(tmp_path, monkeypatch):
    monkeypatch.delenv("JENA_HOME", raising=False)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    home = tmp_path / "jena"
    bat = home / "bat"
    bat.mkdir(parents=True)
    for name in ("riot.bat", "tdb2_tdbloader.bat", "tdb2_tdbquery.bat"):
        (bat / name).write_text("@echo off\n")

    java_home = tmp_path / "fake-java"
    (java_home / "bin").mkdir(parents=True)
    (java_home / "bin" / "java.exe").write_text("")
    monkeypatch.setenv("JAVA_HOME", str(java_home))
    monkeypatch.setenv("JENA_HOME", str(home))
    assert jena_tools.ensure_jena(download=False) == home
    assert jena_tools.find_tdbloader().resolve() == (bat / "tdb2_tdbloader.bat").resolve()
    assert jena_tools.find_tdbquery().resolve() == (bat / "tdb2_tdbquery.bat").resolve()
