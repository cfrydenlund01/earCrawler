from __future__ import annotations

import pytest

from earCrawler.kg.sparql import SPARQLClient


@pytest.fixture()
def client(monkeypatch):
    cli = SPARQLClient("http://localhost:3030/ds/sparql")
    return cli


def test_select_returns_json(monkeypatch, client, requests_mock):
    requests_mock.get(
        "http://localhost:3030/ds/sparql",
        json={"head": {"vars": ["s"]}, "results": {"bindings": []}},
        status_code=200,
    )
    result = client.select("SELECT * WHERE { ?s ?p ?o }")
    assert result["results"]["bindings"] == []


def test_ask_extracts_boolean(client, requests_mock):
    requests_mock.get(
        "http://localhost:3030/ds/sparql",
        json={"boolean": True},
        status_code=200,
    )
    assert client.ask("ASK {}") is True


def test_construct_returns_text(client, requests_mock):
    requests_mock.get(
        "http://localhost:3030/ds/sparql",
        text="<s> <p> <o> .",
        status_code=200,
    )
    assert client.construct("CONSTRUCT WHERE { ?s ?p ?o }") == "<s> <p> <o> ."


def test_update_posts_to_update_endpoint(client, requests_mock):
    requests_mock.post(
        "http://localhost:3030/ds/update",
        status_code=204,
    )
    client.update("INSERT DATA { <s> <p> <o> }")
    assert requests_mock.called
    sent = requests_mock.last_request
    assert sent.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert "update=INSERT+DATA" in sent.text
