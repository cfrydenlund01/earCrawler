from __future__ import annotations

import sys
import importlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
from rdflib import Graph

import pytest

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))


def _import_ingestor():
    module = SimpleNamespace()
    module.CRED_TYPE_GENERIC = 1

    def cred_read(name: str, cred_type: int, flags: int):
        return {"CredentialBlob": b"x"}

    module.CredRead = cred_read
    sys.modules["win32cred"] = module
    ing = importlib.import_module("earCrawler.ingestion.ingest")
    importlib.reload(ing)
    return ing.Ingestor


class StubClient(SimpleNamespace):
    pass


def setup_ingestor(monkeypatch, tmp_path, validate_return=(True, None, ""), loader_exc=None):
    Ingestor = _import_ingestor()
    tg = StubClient()
    fr = StubClient()
    tg.search_entities = lambda q: [{"id": "1"}]
    fr.search_documents = lambda eid: [{"id": "d1"}]

    ing = Ingestor(tg, fr, Path(tmp_path / "tdb"))

    monkeypatch.setattr(ing, "map_entity_to_triples", lambda e: Graph())
    monkeypatch.setattr(ing, "map_document_to_triples", lambda d: Graph())
    monkeypatch.setattr("earCrawler.ingestion.ingest.validate", lambda **kw: validate_return)

    calls = []

    def fake_run(cmd, check):
        calls.append(cmd)
        if loader_exc:
            raise loader_exc

    monkeypatch.setattr("earCrawler.ingestion.ingest.subprocess.run", fake_run)
    return ing, calls


def test_ingest_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ing, calls = setup_ingestor(monkeypatch, tmp_path)
    ing.run("foo")
    assert (tmp_path / "generated-triples.ttl").exists()
    assert calls and calls[0][0] == "tdb2.tdbloader"


def test_shacl_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ing, calls = setup_ingestor(monkeypatch, tmp_path, validate_return=(False, None, "bad"))
    ing.run("foo")
    assert (tmp_path / "generated-triples.ttl").exists()
    assert calls == []


def test_jena_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    exc = subprocess.CalledProcessError(1, "tdb2.tdbloader")
    ing, calls = setup_ingestor(monkeypatch, tmp_path, loader_exc=exc)
    ing.run("foo")
    assert (tmp_path / "generated-triples.ttl").exists()
    assert calls and calls[0][0] == "tdb2.tdbloader"
