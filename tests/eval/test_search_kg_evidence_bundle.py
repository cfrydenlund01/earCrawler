from __future__ import annotations

import json
from pathlib import Path

from scripts.eval import build_search_kg_evidence_bundle as bundle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_registry(tmp_path: Path) -> Path:
    registry_path = tmp_path / "service" / "docs" / "capability_registry.json"
    _write_json(
        registry_path,
        {
            "schema_version": "capability-registry.v1",
            "capabilities": [
                {
                    "id": "api.search",
                    "status": "quarantined",
                    "default_posture": "disabled",
                    "surfaces": ["/v1/search"],
                    "gates": ["EARCRAWLER_API_ENABLE_SEARCH=1"],
                    "notes": "Quarantined search route.",
                },
                {
                    "id": "kg.expansion",
                    "status": "quarantined",
                    "default_posture": "disabled",
                    "surfaces": ["EARCRAWLER_ENABLE_KG_EXPANSION=1"],
                    "gates": ["EARCRAWLER_ENABLE_KG_EXPANSION=1"],
                    "notes": "Quarantined KG expansion.",
                },
            ],
        },
    )
    return registry_path


def _make_optional_runtime_smoke(tmp_path: Path) -> Path:
    path = tmp_path / "dist" / "optional_runtime_smoke.json"
    _write_json(
        path,
        {
            "schema_version": "optional-runtime-smoke.v1",
            "overall_status": "passed",
            "search_mode_checks": [
                {"name": "search_default_off", "status": "passed", "search": {"status_code": 404}},
                {"name": "search_opt_in_on", "status": "passed", "search": {"status_code": 200}},
                {"name": "search_rollback_off", "status": "passed", "search": {"status_code": 404}},
            ],
            "kg_expansion_failure_policy_checks": {
                "status": "passed",
                "checks": {
                    "disable_missing_fuseki": {"status": "passed"},
                    "error_missing_fuseki": {"status": "passed"},
                    "json_stub_expansion": {"status": "passed"},
                },
            },
        },
    )
    return path


def _make_installed_runtime_smoke(tmp_path: Path) -> Path:
    path = tmp_path / "dist" / "installed_runtime_smoke.json"
    _write_json(
        path,
        {
            "schema_version": "installed-runtime-smoke.v1",
            "overall_status": "passed",
            "checks": [
                {"name": "runtime_contract_api_search", "passed": True},
                {"name": "runtime_contract_kg_expansion", "passed": True},
            ],
        },
    )
    return path


def _make_release_validation_evidence(tmp_path: Path, *, complete: bool) -> Path:
    path = tmp_path / "dist" / "release_validation_evidence.json"
    _write_json(
        path,
        {
            "schema_version": "release-validation-evidence.v1",
            "dist_artifacts": {
                "files_verified": 1 if complete else 0,
                "signature_verified": complete,
                "skipped_reason": "" if complete else "checksums file not found",
            },
            "supported_api_smoke": {"status": "passed"},
            "optional_runtime_smoke": {"status": "passed"},
            "installed_runtime_smoke": {"status": "passed"},
        },
    )
    return path


def test_bundle_keeps_search_and_kg_quarantined_when_gate_evidence_is_incomplete(
    tmp_path: Path,
) -> None:
    registry = _make_registry(tmp_path)
    optional_smoke = _make_optional_runtime_smoke(tmp_path)
    installed_smoke = _make_installed_runtime_smoke(tmp_path)
    release_evidence = _make_release_validation_evidence(tmp_path, complete=False)
    out_json = tmp_path / "out" / "bundle.json"
    out_md = tmp_path / "out" / "bundle.md"

    rc = bundle.main(
        [
            "--capability-registry",
            str(registry),
            "--optional-runtime-smoke",
            str(optional_smoke),
            "--installed-runtime-smoke",
            str(installed_smoke),
            "--release-validation-evidence",
            str(release_evidence),
            "--decision-date",
            "2026-03-19",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ]
    )

    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "search-kg-evidence-bundle.v1"
    assert payload["recommendation"] == "Keep Quarantined"
    assert payload["required_smoke_coverage"]["optional_runtime_smoke"]["status"] == "passed"
    assert payload["required_smoke_coverage"]["installed_runtime_smoke"]["status"] == "passed"
    assert payload["required_smoke_coverage"]["release_validation"]["status"] == "incomplete"
    assert any("text-index-enabled Fuseki" in item for item in payload["blocking_gaps"])
    assert "Keep Quarantined" in out_md.read_text(encoding="utf-8")



def test_bundle_marks_ready_for_formal_promotion_review_only_with_complete_evidence(
    tmp_path: Path,
) -> None:
    registry = _make_registry(tmp_path)
    optional_smoke = _make_optional_runtime_smoke(tmp_path)
    installed_smoke = _make_installed_runtime_smoke(tmp_path)
    release_evidence = _make_release_validation_evidence(tmp_path, complete=True)
    search_prod_smoke = tmp_path / "evidence" / "search_prod_smoke.json"
    search_operator = tmp_path / "evidence" / "search_operator_evidence.md"
    kg_prod_smoke = tmp_path / "evidence" / "kg_prod_smoke.json"
    search_prod_smoke.parent.mkdir(parents=True, exist_ok=True)
    search_prod_smoke.write_text("{}", encoding="utf-8")
    search_operator.write_text("# operator proof\n", encoding="utf-8")
    kg_prod_smoke.write_text("{}", encoding="utf-8")
    out_json = tmp_path / "out" / "bundle.json"
    out_md = tmp_path / "out" / "bundle.md"

    rc = bundle.main(
        [
            "--capability-registry",
            str(registry),
            "--optional-runtime-smoke",
            str(optional_smoke),
            "--installed-runtime-smoke",
            str(installed_smoke),
            "--release-validation-evidence",
            str(release_evidence),
            "--search-prod-smoke",
            str(search_prod_smoke),
            "--search-operator-evidence",
            str(search_operator),
            "--kg-prod-smoke",
            str(kg_prod_smoke),
            "--decision-date",
            "2026-03-19",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ]
    )

    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["recommendation"] == "Ready for formal promotion review"
    assert payload["blocking_gaps"] == []
    assert "Ready for formal promotion review" in out_md.read_text(encoding="utf-8")
