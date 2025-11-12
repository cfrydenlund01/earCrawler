from __future__ import annotations

import pytest


pytestmark = pytest.mark.enable_socket


@pytest.mark.parametrize(
    "path", ["/health", "/v1/search?q=x", "/v1/entities/urn:example:entity:1"]
)
def test_security_headers_present(app, path: str) -> None:
    res = app.get(path)
    assert res.headers["Cache-Control"] == "no-store"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "no-referrer"


def test_docs_has_csp(app) -> None:
    res = app.get("/docs")
    assert res.status_code == 200
    assert "Content-Security-Policy" in res.headers


def test_problem_details_headers(app) -> None:
    res = app.get("/v1/entities/urn:missing")
    assert res.status_code == 404
    assert res.headers["X-Request-Id"]
    assert res.headers["X-Subject"].startswith("ip:")
