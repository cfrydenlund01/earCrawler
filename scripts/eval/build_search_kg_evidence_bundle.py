from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPABILITY_REGISTRY = REPO_ROOT / "service" / "docs" / "capability_registry.json"
DEFAULT_OPTIONAL_RUNTIME_SMOKE = REPO_ROOT / "dist" / "optional_runtime_smoke.json"
DEFAULT_INSTALLED_RUNTIME_SMOKE = REPO_ROOT / "dist" / "installed_runtime_smoke.json"
DEFAULT_RELEASE_EVIDENCE = REPO_ROOT / "dist" / "release_validation_evidence.json"
DEFAULT_OUT_JSON = REPO_ROOT / "dist" / "search_kg_evidence" / "search_kg_evidence_bundle.json"
DEFAULT_OUT_MD = REPO_ROOT / "dist" / "search_kg_evidence" / "search_kg_evidence_bundle.md"

SEARCH_PHASES = ("search_default_off", "search_opt_in_on", "search_rollback_off")
KG_FAILURE_CHECKS = (
    "disable_missing_fuseki",
    "error_missing_fuseki",
    "json_stub_expansion",
)
INSTALLED_RUNTIME_CHECKS = (
    "runtime_contract_api_search",
    "runtime_contract_kg_expansion",
)
GOVERNING_DOCS = (
    "docs/RunPass9.md",
    "docs/kg_quarantine_exit_gate.md",
    "docs/kg_unquarantine_plan.md",
    "docs/capability_graduation_boundaries.md",
    "docs/ops/windows_single_host_operator.md",
    "docs/ops/release_process.md",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _lookup_capability(registry: Mapping[str, Any], capability_id: str) -> dict[str, Any]:
    for entry in registry.get("capabilities") or []:
        if isinstance(entry, Mapping) and str(entry.get("id")) == capability_id:
            return dict(entry)
    raise KeyError(f"Capability {capability_id!r} not found in registry.")


def _summarize_optional_runtime_smoke(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {
            "present": False,
            "status": "missing",
            "overall_status": "",
            "search_phase_statuses": {},
            "missing_search_phases": list(SEARCH_PHASES),
            "kg_failure_check_statuses": {},
            "missing_kg_failure_checks": list(KG_FAILURE_CHECKS),
        }

    search_statuses: dict[str, str] = {}
    search_phases_raw = payload.get("search_mode_checks") or []
    if isinstance(search_phases_raw, list):
        for item in search_phases_raw:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                if name:
                    search_statuses[name] = str(item.get("status") or "")

    kg_statuses: dict[str, str] = {}
    kg_raw = payload.get("kg_expansion_failure_policy_checks") or {}
    if isinstance(kg_raw, Mapping):
        checks = kg_raw.get("checks") or {}
        if isinstance(checks, Mapping):
            for name, item in checks.items():
                if isinstance(item, Mapping):
                    kg_statuses[str(name)] = str(item.get("status") or "")

    missing_search = [name for name in SEARCH_PHASES if name not in search_statuses]
    missing_kg = [name for name in KG_FAILURE_CHECKS if name not in kg_statuses]

    passed = (
        str(payload.get("schema_version") or "") == "optional-runtime-smoke.v1"
        and str(payload.get("overall_status") or "") == "passed"
        and not missing_search
        and not missing_kg
        and all(search_statuses.get(name) == "passed" for name in SEARCH_PHASES)
        and all(kg_statuses.get(name) == "passed" for name in KG_FAILURE_CHECKS)
    )
    return {
        "present": True,
        "status": "passed" if passed else "failed",
        "overall_status": str(payload.get("overall_status") or ""),
        "search_phase_statuses": search_statuses,
        "missing_search_phases": missing_search,
        "kg_failure_check_statuses": kg_statuses,
        "missing_kg_failure_checks": missing_kg,
    }


def _summarize_installed_runtime_smoke(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {
            "present": False,
            "status": "missing",
            "overall_status": "",
            "check_statuses": {},
            "missing_checks": list(INSTALLED_RUNTIME_CHECKS),
            "failed_checks": [],
        }

    check_statuses: dict[str, bool] = {}
    checks_raw = payload.get("checks") or []
    if isinstance(checks_raw, list):
        for item in checks_raw:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                if name:
                    check_statuses[name] = bool(item.get("passed"))
    missing_checks = [name for name in INSTALLED_RUNTIME_CHECKS if name not in check_statuses]
    failed_checks = [name for name in INSTALLED_RUNTIME_CHECKS if check_statuses.get(name) is False]
    passed = (
        str(payload.get("schema_version") or "") == "installed-runtime-smoke.v1"
        and str(payload.get("overall_status") or "") == "passed"
        and not missing_checks
        and not failed_checks
    )
    return {
        "present": True,
        "status": "passed" if passed else "failed",
        "overall_status": str(payload.get("overall_status") or ""),
        "check_statuses": check_statuses,
        "missing_checks": missing_checks,
        "failed_checks": failed_checks,
    }


def _summarize_release_evidence(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {
            "present": False,
            "status": "missing",
            "dist_files_verified": 0,
            "dist_signature_verified": False,
            "dist_skipped_reason": "missing report",
            "supported_api_smoke_status": "missing",
            "optional_runtime_smoke_status": "missing",
            "installed_runtime_smoke_status": "missing",
        }

    dist_artifacts = payload.get("dist_artifacts") or {}
    supported_api_smoke = payload.get("supported_api_smoke") or {}
    optional_runtime_smoke = payload.get("optional_runtime_smoke") or {}
    installed_runtime_smoke = payload.get("installed_runtime_smoke") or {}
    complete = (
        str(payload.get("schema_version") or "") == "release-validation-evidence.v1"
        and int(dist_artifacts.get("files_verified") or 0) > 0
        and bool(dist_artifacts.get("signature_verified"))
        and not str(dist_artifacts.get("skipped_reason") or "").strip()
        and str(supported_api_smoke.get("status") or "") == "passed"
        and str(optional_runtime_smoke.get("status") or "") == "passed"
        and str(installed_runtime_smoke.get("status") or "") == "passed"
    )
    return {
        "present": True,
        "status": "complete" if complete else "incomplete",
        "dist_files_verified": int(dist_artifacts.get("files_verified") or 0),
        "dist_signature_verified": bool(dist_artifacts.get("signature_verified")),
        "dist_skipped_reason": str(dist_artifacts.get("skipped_reason") or ""),
        "supported_api_smoke_status": str(supported_api_smoke.get("status") or ""),
        "optional_runtime_smoke_status": str(optional_runtime_smoke.get("status") or ""),
        "installed_runtime_smoke_status": str(installed_runtime_smoke.get("status") or ""),
    }


def _existing_path(path: Path | None) -> bool:
    return path is not None and path.exists()


def _build_operator_workflow_requirements() -> list[dict[str, str]]:
    return [
        {
            "surface": "/v1/search",
            "requirement": "Provide a deployed-host, text-index-enabled Fuseki workflow in the supported Windows single-host operator path before promotion.",
            "source": "docs/capability_graduation_boundaries.md#1-text-search",
        },
        {
            "surface": "KG expansion",
            "requirement": "Keep KG expansion default-off until release-gated smoke covers the configured success path and the declared failure policy.",
            "source": "docs/capability_graduation_boundaries.md#3-kg-expansion",
        },
        {
            "surface": "Deployed host baseline",
            "requirement": "Do not enable EARCRAWLER_API_ENABLE_SEARCH or EARCRAWLER_ENABLE_KG_EXPANSION on deployed hosts before the quarantine gate passes.",
            "source": "docs/ops/windows_single_host_operator.md",
        },
        {
            "surface": "Release evidence",
            "requirement": "Archive supported API smoke, optional runtime smoke, installed runtime smoke, and release validation evidence together for the review package.",
            "source": "docs/ops/release_process.md",
        },
    ]


def _build_rollback_requirements() -> list[dict[str, str]]:
    return [
        {
            "surface": "/v1/search",
            "rollback": "Disable EARCRAWLER_API_ENABLE_SEARCH, restart the service, and return to API contract artifacts that exclude /v1/search.",
            "source": "docs/capability_graduation_boundaries.md#1-text-search",
        },
        {
            "surface": "KG expansion",
            "rollback": "Disable EARCRAWLER_ENABLE_KG_EXPANSION and return to retrieval-only RAG behavior.",
            "source": "docs/capability_graduation_boundaries.md#3-kg-expansion",
        },
        {
            "surface": "Optional/quarantined validation modes",
            "rollback": "Reset search and KG env vars to 0 and restart the EarCrawler API service.",
            "source": "docs/ops/windows_single_host_operator.md",
        },
    ]


def _build_failure_mode_expectations(optional_smoke: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    kg_checks = {}
    if optional_smoke and isinstance(optional_smoke.get("kg_expansion_failure_policy_checks"), Mapping):
        kg_checks = dict(optional_smoke.get("kg_expansion_failure_policy_checks", {}).get("checks") or {})

    search_statuses: dict[str, Any] = {}
    if optional_smoke and isinstance(optional_smoke.get("search_mode_checks"), list):
        for item in optional_smoke.get("search_mode_checks") or []:
            if isinstance(item, Mapping):
                search_statuses[str(item.get("name") or "")] = item

    return [
        {
            "surface": "/v1/search default-off",
            "expected_behavior": "The route should return 404 when the search gate is disabled.",
            "source": "scripts/optional-runtime-smoke.ps1",
            "current_observation": (
                search_statuses.get("search_default_off", {}).get("search", {}).get("status_code")
                if search_statuses.get("search_default_off")
                else None
            ),
        },
        {
            "surface": "/v1/search opt-in",
            "expected_behavior": "The route should return 200 only when EARCRAWLER_API_ENABLE_SEARCH=1 is set for local validation.",
            "source": "scripts/optional-runtime-smoke.ps1",
            "current_observation": (
                search_statuses.get("search_opt_in_on", {}).get("search", {}).get("status_code")
                if search_statuses.get("search_opt_in_on")
                else None
            ),
        },
        {
            "surface": "KG expansion failure_policy=disable",
            "expected_behavior": "Missing Fuseki should fail closed to no expansion rows rather than silently widening support claims.",
            "source": "docs/kg_quarantine_exit_gate.md#6-failure-behavior-is-defined-and-conservative",
            "current_observation": kg_checks.get("disable_missing_fuseki"),
        },
        {
            "surface": "KG expansion failure_policy=error",
            "expected_behavior": "Missing Fuseki should raise a bounded runtime error when failure_policy=error is selected.",
            "source": "docs/kg_quarantine_exit_gate.md#6-failure-behavior-is-defined-and-conservative",
            "current_observation": kg_checks.get("error_missing_fuseki"),
        },
    ]


def _build_gap_list(
    *,
    optional_summary: Mapping[str, Any],
    installed_summary: Mapping[str, Any],
    release_summary: Mapping[str, Any],
    search_prod_smoke: Path | None,
    search_operator_evidence: Path | None,
    kg_prod_smoke: Path | None,
) -> list[str]:
    gaps: list[str] = []
    if str(optional_summary.get("status")) != "passed":
        gaps.append("Optional runtime smoke does not fully prove the required search/KG gate checks in the current workspace.")
    if str(installed_summary.get("status")) != "passed":
        gaps.append("Installed runtime smoke does not currently prove the quarantined search/KG contract in release shape.")
    if str(release_summary.get("status")) != "complete":
        reason = str(release_summary.get("dist_skipped_reason") or "").strip()
        if reason:
            gaps.append(f"Release validation evidence is incomplete: {reason}.")
        else:
            gaps.append("Release validation evidence is incomplete for the required smoke and distributable-artifact checks.")
    if not _existing_path(search_operator_evidence):
        gaps.append("No operator-owned text-index-enabled Fuseki provisioning/rollback evidence is attached for /v1/search.")
    if not _existing_path(search_prod_smoke):
        gaps.append("No production-like smoke artifact is attached for /v1/search against a real text-index-backed Fuseki runtime path.")
    if not _existing_path(kg_prod_smoke):
        gaps.append("No production-like smoke artifact is attached for KG expansion success through the supported runtime shape.")
    return gaps


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Search/KG Evidence Bundle",
        "",
        f"Decision date: {payload['decision_date']}",
        "",
        f"Recommendation: **{payload['recommendation']}**",
        "",
        "## Capability snapshot",
        "",
    ]
    for capability in payload["capability_snapshot"]:
        lines.extend(
            [
                f"- `{capability['id']}`: `{capability['status']}`",
                f"  - Surfaces: {', '.join(capability['surfaces'])}",
                f"  - Gate: {', '.join(capability['gates']) if capability['gates'] else 'none'}",
            ]
        )

    lines.extend(
        [
            "",
            "## Required smoke coverage",
            "",
            f"- Optional runtime smoke: `{payload['required_smoke_coverage']['optional_runtime_smoke']['status']}`",
            f"- Installed runtime smoke: `{payload['required_smoke_coverage']['installed_runtime_smoke']['status']}`",
            f"- Release validation evidence: `{payload['required_smoke_coverage']['release_validation']['status']}`",
            "",
            "## Blocking gaps",
            "",
        ]
    )
    for gap in payload["blocking_gaps"]:
        lines.append(f"- {gap}")

    lines.extend(
        [
            "",
            "## Governing docs",
            "",
        ]
    )
    for doc in payload["governing_docs"]:
        lines.append(f"- `{doc}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a dated search/KG evidence bundle and go/no-go recommendation."
    )
    parser.add_argument("--capability-registry", type=Path, default=DEFAULT_CAPABILITY_REGISTRY)
    parser.add_argument("--optional-runtime-smoke", type=Path, default=DEFAULT_OPTIONAL_RUNTIME_SMOKE)
    parser.add_argument("--installed-runtime-smoke", type=Path, default=DEFAULT_INSTALLED_RUNTIME_SMOKE)
    parser.add_argument("--release-validation-evidence", type=Path, default=DEFAULT_RELEASE_EVIDENCE)
    parser.add_argument("--search-prod-smoke", type=Path, default=None)
    parser.add_argument("--search-operator-evidence", type=Path, default=None)
    parser.add_argument("--kg-prod-smoke", type=Path, default=None)
    parser.add_argument("--decision-date", default=str(date.today()))
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = parser.parse_args(argv)

    registry = _read_json(args.capability_registry.resolve())
    optional_runtime_smoke = (
        _read_json(args.optional_runtime_smoke.resolve())
        if args.optional_runtime_smoke.resolve().exists()
        else None
    )
    installed_runtime_smoke = (
        _read_json(args.installed_runtime_smoke.resolve())
        if args.installed_runtime_smoke.resolve().exists()
        else None
    )
    release_validation_evidence = (
        _read_json(args.release_validation_evidence.resolve())
        if args.release_validation_evidence.resolve().exists()
        else None
    )

    search_capability = _lookup_capability(registry, "api.search")
    kg_capability = _lookup_capability(registry, "kg.expansion")

    optional_summary = _summarize_optional_runtime_smoke(optional_runtime_smoke)
    installed_summary = _summarize_installed_runtime_smoke(installed_runtime_smoke)
    release_summary = _summarize_release_evidence(release_validation_evidence)

    gaps = _build_gap_list(
        optional_summary=optional_summary,
        installed_summary=installed_summary,
        release_summary=release_summary,
        search_prod_smoke=args.search_prod_smoke.resolve() if args.search_prod_smoke else None,
        search_operator_evidence=args.search_operator_evidence.resolve() if args.search_operator_evidence else None,
        kg_prod_smoke=args.kg_prod_smoke.resolve() if args.kg_prod_smoke else None,
    )
    recommendation = (
        "Ready for formal promotion review" if not gaps else "Keep Quarantined"
    )

    payload = {
        "schema_version": "search-kg-evidence-bundle.v1",
        "created_at_utc": _utc_now_iso(),
        "decision_date": args.decision_date,
        "recommendation": recommendation,
        "capability_snapshot": [
            {
                "id": "api.search",
                "status": search_capability.get("status"),
                "default_posture": search_capability.get("default_posture"),
                "surfaces": search_capability.get("surfaces") or [],
                "gates": search_capability.get("gates") or [],
                "notes": search_capability.get("notes"),
            },
            {
                "id": "kg.expansion",
                "status": kg_capability.get("status"),
                "default_posture": kg_capability.get("default_posture"),
                "surfaces": kg_capability.get("surfaces") or [],
                "gates": kg_capability.get("gates") or [],
                "notes": kg_capability.get("notes"),
            },
        ],
        "required_smoke_coverage": {
            "optional_runtime_smoke": optional_summary,
            "installed_runtime_smoke": installed_summary,
            "release_validation": release_summary,
        },
        "operator_workflow_requirements": _build_operator_workflow_requirements(),
        "rollback_requirements": _build_rollback_requirements(),
        "failure_mode_expectations": _build_failure_mode_expectations(optional_runtime_smoke),
        "blocking_gaps": gaps,
        "evidence_inputs": {
            "capability_registry": _rel(args.capability_registry.resolve()),
            "optional_runtime_smoke": _rel(args.optional_runtime_smoke.resolve()),
            "installed_runtime_smoke": _rel(args.installed_runtime_smoke.resolve()),
            "release_validation_evidence": _rel(args.release_validation_evidence.resolve()),
            "search_prod_smoke": _rel(args.search_prod_smoke.resolve()) if args.search_prod_smoke else None,
            "search_operator_evidence": _rel(args.search_operator_evidence.resolve()) if args.search_operator_evidence else None,
            "kg_prod_smoke": _rel(args.kg_prod_smoke.resolve()) if args.kg_prod_smoke else None,
        },
        "governing_docs": list(GOVERNING_DOCS),
    }

    _write_json(args.out_json.resolve(), payload)
    _write_text(args.out_md.resolve(), _render_markdown(payload))
    print(f"Wrote search/KG evidence bundle: {args.out_json.resolve()}")
    print(f"Wrote search/KG evidence summary: {args.out_md.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

