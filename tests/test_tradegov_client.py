from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest


def _setup_module(api_key: str | None):
    module = types.SimpleNamespace()
    module.CRED_TYPE_GENERIC = 1

    def cred_read(name, cred_type, flags):
        assert name == "earCrawler:tradegov_api"
        if api_key is None:
            raise Exception("missing")
        return {"CredentialBlob": api_key.encode("utf-16")}

    module.CredRead = cred_read
    sys.modules["win32cred"] = module
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    tg = importlib.import_module("api_clients.tradegov_client")
    importlib.reload(tg)
    return tg


def test_list_countries_success(monkeypatch):
    tg = _setup_module("secret")

    def mock_get(url, params=None, timeout=10):
        assert url == "https://api.trade.gov/v1/countries"
        assert params == {"api_key": "secret"}

        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {"ok": True}
        return response

    monkeypatch.setattr(tg.requests, "get", mock_get)
    client = tg.TradeGovClient()
    assert client.list_countries() == {"ok": True}


def test_missing_credentials():
    tg = _setup_module(None)
    with pytest.raises(RuntimeError):
        tg.TradeGovClient()
