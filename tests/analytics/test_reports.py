from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from urllib.error import HTTPError

import pytest

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))


def _make_wrapper(responses):
    class _Wrapper:
        call_count = 0

        def __init__(self, endpoint: str) -> None:
            self.responses = list(responses)

        def setReturnFormat(self, fmt):
            self.fmt = fmt

        def setQuery(self, q: str):
            self.query_str = q

        class _Result:
            def __init__(self, data):
                self.data = data

            def convert(self):
                return self.data

        def query(self):
            _Wrapper.call_count += 1
            resp = self.responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return self._Result(resp)

    return _Wrapper


def _load_reports(monkeypatch, wrapper):
    """Load the reports module with a stubbed SPARQLWrapper."""
    monkeypatch.setenv("SPARQL_ENDPOINT_URL", "http://example.com")

    # Provide a fake SPARQLWrapper module before importing the reports module
    fake_module = types.ModuleType("SPARQLWrapper")
    fake_module.SPARQLWrapper = wrapper
    fake_module.JSON = object()
    exceptions_mod = types.ModuleType("SPARQLWrapper.SPARQLExceptions")
    exceptions_mod.QueryBadFormed = Exception
    monkeypatch.setitem(sys.modules, "SPARQLWrapper", fake_module)
    monkeypatch.setitem(
        sys.modules,
        "SPARQLWrapper.SPARQLExceptions",
        exceptions_mod,
    )

    import earCrawler.analytics.reports as reports
    importlib.reload(reports)
    monkeypatch.setattr(reports.time, "sleep", lambda s: None)
    return reports


def test_count_entities_by_country(monkeypatch):
    data = {
        "results": {
            "bindings": [
                {"country": {"value": "US"}, "count": {"value": "2"}},
                {"country": {"value": "CA"}, "count": {"value": "1"}},
            ]
        }
    }
    wrapper = _make_wrapper([data])
    reports = _load_reports(monkeypatch, wrapper)
    gen = reports.ReportsGenerator()
    result = gen.count_entities_by_country()
    assert result == {"US": 2, "CA": 1}
    for k, v in result.items():
        assert isinstance(k, str)
        assert isinstance(v, int)


def test_count_documents_by_year(monkeypatch):
    data = {
        "results": {
            "bindings": [
                {"year": {"value": "2023"}, "count": {"value": "5"}},
                {"year": {"value": "2024"}, "count": {"value": "7"}},
            ]
        }
    }
    wrapper = _make_wrapper([data])
    reports = _load_reports(monkeypatch, wrapper)
    gen = reports.ReportsGenerator()
    result = gen.count_documents_by_year()
    assert result == {2023: 5, 2024: 7}
    for k, v in result.items():
        assert isinstance(k, int)
        assert isinstance(v, int)


def test_get_document_count_for_entity(monkeypatch):
    data = {"results": {"bindings": [{"count": {"value": "4"}}]}}
    wrapper = _make_wrapper([data])
    reports = _load_reports(monkeypatch, wrapper)
    gen = reports.ReportsGenerator()
    count = gen.get_document_count_for_entity("E1")
    assert count == 4
    assert isinstance(count, int)


def test_http_error_retry(monkeypatch):
    err = HTTPError(None, 500, "boom", None, None)
    wrapper = _make_wrapper([err, err, err])
    reports = _load_reports(monkeypatch, wrapper)
    gen = reports.ReportsGenerator()
    with pytest.raises(reports.AnalyticsError):
        gen.count_entities_by_country()
    assert wrapper.call_count == 3
