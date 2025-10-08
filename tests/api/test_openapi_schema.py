from __future__ import annotations

from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.enable_socket


def test_openapi_schema_matches_routes(app) -> None:
    spec_path = Path("service/openapi/openapi.yaml")
    data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert data["openapi"].startswith("3.1")
    spec_paths = set(data["paths"].keys())
    app_paths = {route.path for route in app.app.routes if getattr(route, "methods", None)}
    for path in spec_paths:
        assert path in app_paths, f"Path {path} missing from application routes"
    assert "/health" in spec_paths
    assert data["components"]["schemas"]["ProblemDetails"]["type"] == "object"
