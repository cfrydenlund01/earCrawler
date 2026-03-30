from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("require_pwsh")

ROOT = Path(__file__).resolve().parents[2]


def run_ps(script: str, *args: str, env: dict[str, str] | None = None, check: bool = True):
    cmd = ["pwsh", "-File", str(ROOT / script)] + list(args)
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    return subprocess.run(cmd, cwd=ROOT, env=merged_env, check=check)


def test_optional_runtime_smoke_runs_without_local_adapter_artifact(tmp_path: Path) -> None:
    report_path = tmp_path / "optional_runtime_smoke.json"
    run_ps(
        "scripts/optional-runtime-smoke.ps1",
        "-Host",
        "127.0.0.1",
        "-Port",
        "9013",
        "-SkipLocalAdapter",
        "-ReportPath",
        str(report_path),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "optional-runtime-smoke.v1"
    assert payload["overall_status"] == "passed"
    assert payload["kg_expansion_failure_policy_checks"]["status"] == "passed"
    assert payload["search_kg_production_like"]["status"] in {"passed", "failed", "skipped"}
    assert payload["local_adapter_check"]["status"] == "skipped"

    phase_names = [phase["name"] for phase in payload["search_mode_checks"]]
    assert phase_names == ["search_default_off", "search_opt_in_on", "search_rollback_off"]
    assert payload["search_mode_checks"][0]["search"]["status_code"] == 404
    assert payload["search_mode_checks"][1]["search"]["status_code"] == 200
    assert payload["search_mode_checks"][2]["search"]["status_code"] == 404
    for phase in payload["search_mode_checks"]:
        assert phase["api_start_lifecycle"]["schema_version"] == "api-start-lifecycle.v1"
        assert phase["api_stop_lifecycle"]["schema_version"] == "api-stop-lifecycle.v1"
        assert phase["api_start_lifecycle"]["overall_status"] == "passed"
        assert phase["api_stop_lifecycle"]["status"] in {"stopped", "stale_state_removed"}
