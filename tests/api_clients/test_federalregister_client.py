from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _import_client():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    module = importlib.import_module("api_clients.federalregister_client")
    importlib.reload(module)
    return module


def test_search_documents_no_key(requests_mock):
    fr = _import_client()
    resp = {"results": [{"document_number": "1"}]}
    m = requests_mock.get(
        "https://api.federalregister.gov/v1/documents",
        json=resp,
    )
    client = fr.FederalRegisterClient()
    results = list(client.search_documents("foo"))
    assert results == [{"document_number": "1"}]
    assert m.call_count == 1
    assert "api_key" not in m.last_request.qs


def test_get_document(requests_mock):
    fr = _import_client()
    m = requests_mock.get(
        "https://api.federalregister.gov/v1/documents/1",
        json={"id": 1},
    )
    client = fr.FederalRegisterClient()
    result = client.get_document("1")
    assert result == {"id": 1}
    assert m.call_count == 1
