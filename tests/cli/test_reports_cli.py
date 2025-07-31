from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from click.testing import CliRunner

root = Path(__file__).resolve().parents[2]  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(root))  # noqa: E402

import earCrawler.cli.reports_cli as reports_cli  # noqa: E402


def _reload() -> Any:
    importlib.reload(reports_cli)
    return reports_cli


def test_entities_by_country_success(monkeypatch, requests_mock):
    monkeypatch.setenv("ANALYTICS_SERVICE_URL", "http://example.com")
    _reload()
    requests_mock.get(
        "http://example.com/reports/entities-by-country",
        json={"entities_by_country": {"US": 2, "CA": 1}},
    )
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["entities-by-country"])
    assert result.exit_code == 0
    assert "US" in result.output
    assert "CA" in result.output


def test_documents_by_year_success(monkeypatch, requests_mock):
    monkeypatch.setenv("ANALYTICS_SERVICE_URL", "http://example.com")
    _reload()
    requests_mock.get(
        "http://example.com/reports/documents-by-year",
        json={"documents_by_year": {"2023": 5, "2024": 7}},
    )
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["documents-by-year"])
    assert result.exit_code == 0
    assert "2023" in result.output
    assert "7" in result.output


def test_document_count_success(monkeypatch, requests_mock):
    monkeypatch.setenv("ANALYTICS_SERVICE_URL", "http://example.com")
    _reload()
    requests_mock.get(
        "http://example.com/reports/document-count/E1",
        json={"entity_id": "E1", "document_count": 3},
    )
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["document-count", "E1"])
    assert result.exit_code == 0
    assert "Entity E1 has 3 documents" in result.output


def test_http_error(monkeypatch, requests_mock):
    monkeypatch.setenv("ANALYTICS_SERVICE_URL", "http://example.com")
    _reload()
    requests_mock.get(
        "http://example.com/reports/entities-by-country",
        status_code=502,
        text="bad",
    )
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["entities-by-country"])
    assert result.exit_code != 0
    assert "502" in result.output


def test_malformed_json(monkeypatch, requests_mock):
    monkeypatch.setenv("ANALYTICS_SERVICE_URL", "http://example.com")
    _reload()
    requests_mock.get(
        "http://example.com/reports/entities-by-country",
        text="not json",
    )
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["entities-by-country"])
    assert result.exit_code != 0
    assert "Malformed JSON" in result.output


def test_timeout(monkeypatch):
    monkeypatch.setenv("ANALYTICS_SERVICE_URL", "http://example.com")
    _reload()

    def raiser(*_a, **_kw):
        raise reports_cli.requests.exceptions.Timeout("timeout")

    monkeypatch.setattr(reports_cli.requests, "get", raiser)
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["documents-by-year"])
    assert result.exit_code != 0
    assert "timeout" in result.output


def test_missing_env(monkeypatch):
    monkeypatch.delenv("ANALYTICS_SERVICE_URL", raising=False)
    _reload()
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["documents-by-year"])
    assert result.exit_code != 0
    assert "ANALYTICS_SERVICE_URL" in result.output


def test_empty_entity_id(monkeypatch):
    monkeypatch.setenv("ANALYTICS_SERVICE_URL", "http://example.com")
    _reload()
    runner = CliRunner()
    result = runner.invoke(reports_cli.reports, ["document-count", " "])
    assert result.exit_code != 0
    assert "entity_id" in result.output
