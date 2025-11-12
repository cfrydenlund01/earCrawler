import json
import re
from pathlib import Path


def test_versions_json_schema():
    data = json.loads(Path("tools/versions.json").read_text())
    assert "jena" in data and "fuseki" in data and "python" in data
    for key in ["jena", "fuseki"]:
        info = data[key]
        assert "version" in info
        sha = info.get("sha512")
        assert isinstance(sha, str)
        assert re.fullmatch(r"[0-9a-fA-F]{128}", sha)
    py = data["python"]
    assert py.get("lock")
    assert py.get("win_lock")
