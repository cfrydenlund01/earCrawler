from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import pytest

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import Template, TemplateRegistry


pytestmark = pytest.mark.enable_socket


class FailingFuseki:
    async def query(
        self, template: Template, query: str
    ):  # pragma: no cover - simple stub
        raise RuntimeError("fuseki offline")


@pytest.fixture(autouse=True)
def _enable_socket_fixture(socket_enabled):
    yield


def test_health_endpoint_reports_checks():
    settings = ApiSettings(fuseki_url=None)
    registry = TemplateRegistry.load_default()
    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "pass"
    readiness = payload["readiness"]
    assert readiness["status"] == "pass"
    checks = readiness["checks"]
    assert "fuseki" in checks
    assert checks["fuseki"]["status"] == "pass"
    assert checks["disk"]["status"] in {"pass", "fail"}
    assert payload["live_sources"]["status"] == "unknown"
    assert payload["live_sources"]["reason"] in {
        "manifest_missing",
        "no_upstream_status",
    }


def test_health_endpoint_degraded_on_fuseki_failure():
    settings = ApiSettings(fuseki_url=None)
    registry = TemplateRegistry.load_default()
    app = create_app(
        settings=settings, registry=registry, fuseki_client=FailingFuseki()
    )
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["readiness"]["status"] == "fail"
    assert payload["readiness"]["checks"]["fuseki"]["status"] == "fail"


def test_health_endpoint_reports_live_sources_degraded_and_missing_credentials(
    tmp_path: Path, monkeypatch
):
    now = datetime.now(timezone.utc)
    manifest = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "upstream_status": [
            {
                "source": "federalregister",
                "operation": "get_document",
                "state": "ok",
                "timestamp": (now - timedelta(minutes=5)).isoformat().replace(
                    "+00:00", "Z"
                ),
                "cache_hit": True,
                "cache_age_seconds": 90.5,
            },
            {
                "source": "tradegov",
                "operation": "search",
                "state": "missing_credentials",
                "timestamp": (now - timedelta(minutes=3)).isoformat().replace(
                    "+00:00", "Z"
                ),
                "message": "TRADEGOV_API_KEY missing",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("EARCRAWLER_SOURCE_MANIFEST_PATH", str(manifest_path))

    settings = ApiSettings(fuseki_url=None)
    registry = TemplateRegistry.load_default()
    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    live = payload["live_sources"]
    assert live["status"] == "degraded"
    assert live["summary"]["degraded"] == 1
    assert live["summary"]["healthy"] == 1
    assert live["summary"]["partially_degraded"] is True
    assert live["failure_taxonomy"]["state_counts"]["ok"] == 1
    assert live["failure_taxonomy"]["state_counts"]["missing_credentials"] == 1
    assert live["failure_taxonomy"]["degraded_state_counts"]["missing_credentials"] == 1

    by_source = {entry["source"]: entry for entry in live["sources"]}
    assert by_source["tradegov"]["availability"] == "missing_credentials"
    assert by_source["tradegov"]["status"] == "degraded"
    assert by_source["tradegov"]["state_counts"]["missing_credentials"] == 1
    assert by_source["federalregister"]["freshness"] == "fresh"
    assert by_source["federalregister"]["latest_cache_hit"] is True
    assert by_source["federalregister"]["latest_cache_age_seconds"] == 90.5


def test_health_endpoint_reports_stale_live_sources(tmp_path: Path, monkeypatch):
    now = datetime.now(timezone.utc)
    manifest = {
        "generated_at": (now - timedelta(hours=30)).isoformat().replace("+00:00", "Z"),
        "upstream_status": [
            {
                "source": "federalregister",
                "operation": "search_documents",
                "state": "ok",
                "timestamp": (now - timedelta(hours=12)).isoformat().replace(
                    "+00:00", "Z"
                ),
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("EARCRAWLER_SOURCE_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("EARCRAWLER_SOURCE_STALE_AFTER_SECONDS", "300")

    settings = ApiSettings(fuseki_url=None)
    registry = TemplateRegistry.load_default()
    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    live = payload["live_sources"]
    assert live["status"] == "stale"
    assert live["summary"]["stale"] == 1
    assert live["sources"][0]["freshness"] == "stale"
    assert live["failure_taxonomy"]["state_counts"]["ok"] == 1
