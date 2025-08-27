import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from earCrawler.kg.loader import load_tdb
from earCrawler.utils import jena_tools


def test_load_tdb_autoinstall_downloads_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        jena_tools, "_tdbloader_path", lambda home: home / "bat" / "tdb2.tdbloader.bat"
    )
    monkeypatch.delenv("JENA_VERSION", raising=False)

    ttl = Path("foo.ttl")
    ttl.write_text("")

    downloads: list[str] = []

    def fake_urlretrieve(url, filename):
        downloads.append(url)
        version = os.environ.get("JENA_VERSION", "5.3.0")
        with zipfile.ZipFile(filename, "w") as zf:
            zf.writestr(f"apache-jena-{version}/bat/tdb2.tdbloader.bat", "")
            zf.writestr("payload.bin", os.urandom(6 * 1024 * 1024))

    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

    calls: list[list[str]] = []

    def fake_check_call(cmd, shell=False, stderr=None):
        calls.append(cmd)
        return 0

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    load_tdb(ttl, Path("mydb"))
    jena_home = Path("tools/jena")
    loader = jena_home / "bat" / "tdb2.tdbloader.bat"
    assert loader.is_file()
    assert calls and Path(calls[0][0]) == loader.resolve()
    assert len(downloads) == 1

    load_tdb(ttl, Path("mydb2"))
    assert len(downloads) == 1
