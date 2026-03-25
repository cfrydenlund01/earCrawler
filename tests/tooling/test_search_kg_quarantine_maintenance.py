from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_search_kg_quarantine_maintenance_boundary_is_documented() -> None:
    decision = _read("docs/search_kg_quarantine_decision_package_2026-03-19.md")
    gate = _read("docs/kg_quarantine_exit_gate.md")
    capability_doc = _read("docs/capability_graduation_boundaries.md")
    readme = _read("README.md")
    runbook = _read("RUNBOOK.md")
    service_index = _read("service/docs/index.md")
    operator_guide = _read("docs/ops/windows_single_host_operator.md")

    assert "## Maintenance Posture While Quarantined" in decision
    assert "not active promotion" in decision
    assert "maintenance posture is intentionally narrow" in decision
    assert "preserve the quarantine" in gate
    assert "promotion-like support obligations" in gate
    assert "Current planning rule:" in capability_doc
    assert "do not treat promotion of text search as active near-term work" in capability_doc
    assert "do not treat promotion of KG expansion as active near-term work" in capability_doc
    assert "docs/search_kg_quarantine_decision_package_2026-03-19.md" in capability_doc
    assert "docs/search_kg_quarantine_decision_package_2026-03-19.md" in readme
    assert "docs/search_kg_quarantine_decision_package_2026-03-19.md" in runbook
    assert "docs/search_kg_quarantine_decision_package_2026-03-19.md" in service_index
    assert "Do not enable `EARCRAWLER_API_ENABLE_SEARCH` or `EARCRAWLER_ENABLE_KG_EXPANSION`" in operator_guide


def test_search_kg_quarantine_registry_stays_default_off() -> None:
    registry = json.loads(_read("service/docs/capability_registry.json"))
    entries = {entry["id"]: entry for entry in registry["capabilities"]}

    assert entries["api.search"]["status"] == "quarantined"
    assert entries["api.search"]["default_posture"] == "disabled"
    assert entries["api.search"]["contract_artifacts"] == "excluded_by_default"
    assert entries["kg.expansion"]["status"] == "quarantined"
    assert entries["kg.expansion"]["default_posture"] == "disabled"
