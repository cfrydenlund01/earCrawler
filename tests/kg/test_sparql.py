import json
from pathlib import Path

from click.testing import CliRunner

import earCrawler.cli.__main__ as cli
import earCrawler.kg.sparql as sparql


def test_kg_query_select(tmp_path, monkeypatch):
    data = {
        "head": {"vars": ["s"]},
        "results": {
            "bindings": [
                {"s": {"type": "uri", "value": "a"}},
                {"s": {"type": "uri", "value": "b"}},
            ]
        },
    }

    class Resp:
        status_code = 200

        def json(self):
            return data

    def fake_get(self, url, params=None, headers=None, timeout=None):
        return Resp()

    monkeypatch.setattr(sparql.requests.Session, "get", fake_get)
    runner = CliRunner()
    out = tmp_path / "rows.json"
    result = runner.invoke(cli.kg_query, ["--sparql", "SELECT * WHERE { ?s ?p ?o }", "-o", str(out)])
    assert result.exit_code == 0
    content = json.loads(out.read_text())
    assert len(content["results"]["bindings"]) == 2


def test_kg_query_ask(tmp_path, monkeypatch):
    class Resp:
        status_code = 200

        def json(self):
            return {"boolean": True}

    def fake_get(self, url, params=None, headers=None, timeout=None):
        return Resp()

    monkeypatch.setattr(sparql.requests.Session, "get", fake_get)
    runner = CliRunner()
    out = tmp_path / "ask.json"
    result = runner.invoke(cli.kg_query, ["--form", "ask", "--sparql", "ASK { }", "-o", str(out)])
    assert result.exit_code == 0
    content = json.loads(out.read_text())
    assert content["boolean"] is True


def test_kg_query_construct(tmp_path, monkeypatch):
    class Resp:
        status_code = 200
        text = "<http://example.org/a> <http://example.org/b> <http://example.org/c> ."

    def fake_get(self, url, params=None, headers=None, timeout=None):
        return Resp()

    monkeypatch.setattr(sparql.requests.Session, "get", fake_get)
    runner = CliRunner()
    out = tmp_path / "graph.nt"
    result = runner.invoke(
        cli.kg_query,
        ["--form", "construct", "--sparql", "CONSTRUCT WHERE { ?s ?p ?o }", "-o", str(out)],
    )
    assert result.exit_code == 0
    text = out.read_text()
    assert "example.org/a" in text
