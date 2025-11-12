from __future__ import annotations

from pathlib import Path

import json


def test_registry_templates_exist() -> None:
    registry_path = Path("service/templates/registry.json")
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    for entry in data.values():
        template_path = Path("service/templates") / entry["file"]
        assert template_path.exists(), f"Missing template {template_path}"
        content = template_path.read_text(encoding="utf-8")
        assert (
            "ORDER BY" in content
        ), f"Template {template_path} must have deterministic ordering"
        assert (
            "SERVICE" not in content.upper()
        ), f"Template {template_path} must not call remote SERVICE"
