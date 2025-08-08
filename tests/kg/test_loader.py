from pathlib import Path
from unittest.mock import patch

from earCrawler.kg.loader import load_tdb


def test_load_tdb_invokes_tdbloader_and_creates_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("foo.ttl").write_text("")
    with patch("subprocess.check_call") as mock_call:
        load_tdb(Path("foo.ttl"), Path("mydb"))
        mock_call.assert_called_once_with(
            ["tdb2.tdbloader", "--loc", "mydb", "foo.ttl"]
        )
    assert Path("mydb").is_dir()
