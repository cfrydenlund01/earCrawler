from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import requests


def _setup_module(monkeypatch, responses):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    module = importlib.import_module("api_clients.federal_register_client")
    importlib.reload(module)

    class DummySession:
        def __init__(self):
            self.calls = 0

        def mount(self, *args, **kwargs):
            pass

        def get(self, url, params=None, timeout=10):
            assert url == "https://www.federalregister.gov/api/v1/documents.json"
            resp = responses[self.calls]
            self.calls += 1
            return resp

    dummy = DummySession()
    monkeypatch.setattr(module.requests, "Session", lambda: dummy)
    return module, dummy


def _create_responses():
    responses = []
    for status in [500, 502, 200]:
        resp = Mock()
        resp.status_code = status
        if status >= 400:
            err = requests.HTTPError()
            err.response = Mock(status_code=status)
            resp.raise_for_status.side_effect = err
        else:
            resp.raise_for_status = Mock()
        resp.json.return_value = {"status": status}
        responses.append(resp)
    return responses


def test_list_documents_retries(monkeypatch):
    responses = _create_responses()
    module, dummy = _setup_module(monkeypatch, responses)
    client = module.FederalRegisterClient()
    result = client.list_documents({"per_page": 5})
    assert dummy.calls == 3
    assert result == {"status": 200}
