from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_KG_NAME = "kg" + "_service"
LEGACY_SPARQL_NAME = "sparql" + "_service"
SEARCH_ROOTS = (
    Path("README.md"),
    Path("docker"),
    Path("container"),
    Path("service"),
    Path("scripts"),
    Path("earCrawler"),
    Path("tests"),
)
ALLOWED_KG_MATCHES = {
    Path("README.md"),
    Path("earCrawler/service/legacy") / (LEGACY_KG_NAME + ".py"),
    Path("service/docs/index.md"),
}
ALLOWED_SPARQL_MATCHES = {
    Path("README.md"),
    Path("earCrawler/service") / (LEGACY_SPARQL_NAME + ".py"),
    Path("service/docs/index.md"),
    Path("tests/service/test_sparql_service.py"),
    Path("tests/tooling/test_runtime_service_surface.py"),
}


def _grep_files(pattern: str) -> set[Path]:
    search_roots = [str(path) for path in SEARCH_ROOTS if (REPO_ROOT / path).exists()]
    if shutil.which("rg"):
        proc = subprocess.run(
            ["rg", "-l", pattern, *search_roots],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                proc.stderr.strip() or f"rg failed with exit {proc.returncode}"
            )
        return {Path(line.strip()) for line in proc.stdout.splitlines() if line.strip()}

    matches: set[Path] = set()
    for relative in SEARCH_ROOTS:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        if path.is_file():
            files = [path]
        else:
            files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
        for candidate in files:
            try:
                text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if pattern in text:
                matches.add(candidate.relative_to(REPO_ROOT))
    return matches


def test_legacy_name_only_appears_in_allowed_quarantine_notes() -> None:
    assert _grep_files(LEGACY_KG_NAME) == ALLOWED_KG_MATCHES


def test_legacy_sparql_service_only_appears_in_allowed_quarantine_notes() -> None:
    assert _grep_files(LEGACY_SPARQL_NAME) == ALLOWED_SPARQL_MATCHES


def test_runtime_service_entrypoints_use_api_server() -> None:
    api_start = (REPO_ROOT / "scripts/api-start.ps1").read_text(encoding="utf-8")
    assert "service.api_server.server:app" in api_start

    service_config = (REPO_ROOT / "service/windows/SERVICE_CONFIG.md").read_text(
        encoding="utf-8"
    )
    assert "service.api_server.server:app" in service_config

    install_doc = (REPO_ROOT / "service/windows/INSTALL_SERVICE.md").read_text(
        encoding="utf-8"
    )
    assert "service.api_server.server:app" in install_doc


def test_wheel_packaging_includes_service_runtime_surface() -> None:
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    includes = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    dependencies = pyproject["project"]["dependencies"]

    assert "service*" in includes
    assert package_data["service"] == [
        "config/*.yml",
        "docs/*.md",
        "openapi/*.yaml",
        "templates/*.json",
        "templates/*.rq",
    ]
    assert set(package_data["earCrawler.sparql"]) == {"*.sparql", "*.rq"}
    for requirement in ("httpx", "keyring", "tenacity", "uvicorn"):
        assert any(
            str(dep).lower().startswith(requirement) for dep in dependencies
        ), f"Missing runtime dependency for packaged service import: {requirement}"


def test_wheel_smoke_validates_kg_expansion_template_resource() -> None:
    smoke_script = (REPO_ROOT / "scripts" / "package-wheel-smoke.ps1").read_text(
        encoding="utf-8"
    )

    assert '("earCrawler.sparql", "kg_expand_by_section_id.rq")' in smoke_script
    assert "SPARQLTemplateGateway" in smoke_script
    assert "kg_expand_by_section_id" in smoke_script


def test_repo_does_not_ship_container_runtime_artifacts() -> None:
    ci_workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release_workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    assert not (REPO_ROOT / "docker/api.Dockerfile").exists()
    assert not (REPO_ROOT / "docker/rag.Dockerfile").exists()
    assert not (REPO_ROOT / "container/README.md").exists()
    assert not (REPO_ROOT / "container/earcrawler.def").exists()
    assert "docker/rag.Dockerfile" not in ci_workflow
    assert "docker/api.Dockerfile" not in ci_workflow
    assert "validate-container:" not in ci_workflow
    assert "docker/login-action@" not in ci_workflow
    assert "docker/setup-buildx-action@" not in ci_workflow
    assert "docker/setup-qemu-action@" not in ci_workflow
    assert "container/earcrawler.def" not in ci_workflow
    assert "/api:${{ github.ref_name }}" not in ci_workflow
    assert "/rag:${{ github.ref_name }}" not in ci_workflow
    assert "ghcr.io/" not in ci_workflow
    assert "ghcr.io/" not in release_workflow


def test_repo_does_not_ship_placeholder_training_surface() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert not (REPO_ROOT / "agent").exists()
    assert not (REPO_ROOT / "models" / "legalbert").exists()
    assert not (REPO_ROOT / "earCrawler" / "quant" / "__init__.py").exists()
    assert (
        "supported model-training, fine-tuning, agent, or quantization stack" in readme
    )
    assert "docs/model_training_surface_adr.md" in readme


def test_phase5_base_model_selection_is_recorded_as_planning_only() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    adr = (REPO_ROOT / "docs" / "model_training_surface_adr.md").read_text(
        encoding="utf-8"
    )
    execution_plan = (
        REPO_ROOT / "docs" / "Archive" / "earCrawler_execution_plan_pass6.md"
    ).read_text(encoding="utf-8")
    config_record = (
        REPO_ROOT / "config" / "training_model_selection.example.env"
    ).read_text(encoding="utf-8")

    assert "Qwen/Qwen2.5-7B-Instruct" in readme
    assert "Qwen/Qwen2.5-7B-Instruct" in adr
    assert "planning-only" in adr
    assert "Task 5.1" in execution_plan
    assert "Qwen/Qwen2.5-7B-Instruct" in config_record
    assert "TRAINING_MODEL_STATUS=planning_only" in config_record
    assert "This file is not consumed by the current runtime" in config_record


def test_phase5_training_contract_is_recorded_and_separated() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    adr = (REPO_ROOT / "docs" / "model_training_surface_adr.md").read_text(
        encoding="utf-8"
    )
    contract = (REPO_ROOT / "docs" / "model_training_contract.md").read_text(
        encoding="utf-8"
    )
    execution_plan = (
        REPO_ROOT / "docs" / "Archive" / "earCrawler_execution_plan_pass6.md"
    ).read_text(encoding="utf-8")
    config_record = (
        REPO_ROOT / "config" / "training_input_contract.example.json"
    ).read_text(encoding="utf-8")

    assert "docs/model_training_contract.md" in readme
    assert "docs/model_training_contract.md" in adr
    assert "approved offline snapshot manifest and payload" in contract
    assert "retrieval-corpus.v1" in contract
    assert "A local KG is NOT required" in contract
    assert "eval/*.jsonl" in contract
    assert "future benchmark data remains deferred" in adr
    assert "Task 5.2" in execution_plan
    assert '"schema_version": "training-input-contract.v1"' in config_record
    assert '"eval/*.jsonl"' in config_record
    assert "not require a local KG" in config_record


def test_phase5_first_finetune_pass_is_recorded_with_repeatable_commands() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    adr = (REPO_ROOT / "docs" / "model_training_surface_adr.md").read_text(
        encoding="utf-8"
    )
    contract = (REPO_ROOT / "docs" / "model_training_contract.md").read_text(
        encoding="utf-8"
    )
    runbook = (REPO_ROOT / "docs" / "model_training_first_pass.md").read_text(
        encoding="utf-8"
    )
    execution_plan = (
        REPO_ROOT / "docs" / "Archive" / "earCrawler_execution_plan_pass6.md"
    ).read_text(encoding="utf-8")
    config_record = (
        REPO_ROOT / "config" / "training_first_pass.example.json"
    ).read_text(encoding="utf-8")

    assert "docs/model_training_first_pass.md" in readme
    assert "Phase 5.3" in adr
    assert "scripts/training/run_phase5_finetune.py" in contract
    assert "Task 5.3" in execution_plan
    assert "Implementation status (March 11, 2026)" in execution_plan
    assert "dist/training/<run_id>/run_metadata.json" in runbook
    assert "scripts/training/inference_smoke.py" in runbook
    assert '"schema_version": "training-run-config.v1"' in config_record
    assert '"base_model": "Qwen/Qwen2.5-7B-Instruct"' in config_record
    assert (REPO_ROOT / "scripts" / "training" / "run_phase5_finetune.py").exists()
    assert (REPO_ROOT / "scripts" / "training" / "inference_smoke.py").exists()
    assert (REPO_ROOT / "scripts" / "training" / "run_phase5_finetune.ps1").exists()


def test_six_record_derivative_corpus_is_experimental_only() -> None:
    training_contract = (REPO_ROOT / "docs" / "model_training_contract.md").read_text(
        encoding="utf-8"
    )
    first_pass = (REPO_ROOT / "docs" / "model_training_first_pass.md").read_text(
        encoding="utf-8"
    )
    rebuild_script = (
        REPO_ROOT / "scripts" / "rag" / "rebuild_retrieval_corpus_from_fr_sections.py"
    ).read_text(encoding="utf-8")

    assert not (REPO_ROOT / "data" / "retrieval_corpus.jsonl").exists()
    assert (
        REPO_ROOT
        / "data"
        / "experimental"
        / "retrieval_corpus_6_record_fr_sections.jsonl"
    ).exists()
    assert "data/retrieval_corpus.jsonl" not in first_pass
    assert "data/faiss/retrieval_corpus.jsonl" in first_pass
    assert "data/experimental/retrieval_corpus_6_record_fr_sections.jsonl" in first_pass
    assert "data/experimental/retrieval_corpus_6_record_fr_sections.jsonl" in training_contract
    assert "data/experimental/retrieval_corpus_6_record_fr_sections.jsonl" in rebuild_script


def test_phase5_local_adapter_runtime_is_gated_and_documented() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "RUNBOOK.md").read_text(encoding="utf-8")
    adr = (REPO_ROOT / "docs" / "model_training_surface_adr.md").read_text(
        encoding="utf-8"
    )
    runbook_task = (REPO_ROOT / "docs" / "model_training_first_pass.md").read_text(
        encoding="utf-8"
    )
    execution_plan = (
        REPO_ROOT / "docs" / "Archive" / "earCrawler_execution_plan_pass6.md"
    ).read_text(encoding="utf-8")
    llm_env = (REPO_ROOT / "config" / "llm_secrets.example.env").read_text(
        encoding="utf-8"
    )
    requirements_gpu = (REPO_ROOT / "requirements-gpu.txt").read_text(
        encoding="utf-8"
    )
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "LLM_PROVIDER=local_adapter" in readme
    assert "EARCRAWLER_ENABLE_LOCAL_LLM=1" in readme
    assert "scripts\\local_adapter_smoke.ps1" in readme or "scripts/local_adapter_smoke.ps1" in readme
    assert "Task 5.4" in adr
    assert "run_metadata.json" in adr
    assert "inference_smoke.json" in adr
    assert "Task 5.4" in runbook_task
    assert "Implementation status (March 11, 2026)" in execution_plan
    assert "local_adapter" in execution_plan
    assert "EARCRAWLER_LOCAL_LLM_ADAPTER_DIR" in llm_env
    assert "EARCRAWLER_LOCAL_LLM_BASE_MODEL" in llm_env
    assert "peft==0.11.1" in requirements_gpu
    assert "peft==0.11.1" in pyproject
    assert (
        REPO_ROOT / "earCrawler" / "rag" / "local_adapter_runtime.py"
    ).exists()
    assert (REPO_ROOT / "scripts" / "local_adapter_smoke.ps1").exists()


def test_phase6_benchmark_plan_targets_the_production_candidate() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    execution_plan = (
        REPO_ROOT / "docs" / "Archive" / "earCrawler_execution_plan_pass6.md"
    ).read_text(encoding="utf-8")
    benchmark_plan = (
        REPO_ROOT / "docs" / "production_candidate_benchmark_plan.md"
    ).read_text(encoding="utf-8")

    assert "docs/production_candidate_benchmark_plan.md" in readme
    assert "Task 6.1" in execution_plan
    assert "Implementation status (March 11, 2026)" in execution_plan
    assert "ear_compliance.v2" in benchmark_plan
    assert "entity_obligations.v2" in benchmark_plan
    assert "unanswerable.v2" in benchmark_plan
    assert "local_adapter" in benchmark_plan
    assert "dist/training/<run_id>/" in benchmark_plan
    assert "eval_rag_llm.py" in benchmark_plan


def test_repo_documents_runtime_vs_research_boundary() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "RUNBOOK.md").read_text(encoding="utf-8")
    boundary_doc = (REPO_ROOT / "docs/runtime_research_boundary.md").read_text(
        encoding="utf-8"
    )
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "docs/runtime_research_boundary.md" in readme
    assert "docs/runtime_research_boundary.md" in runbook
    assert "supported product/runtime surface" in boundary_doc
    assert "Research/" in boundary_doc
    assert "not a supported runtime surface" in gitignore


def test_repo_publishes_repository_status_index_for_onboarding() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    start_here = (
        REPO_ROOT / "docs" / "start_here_supported_paths.md"
    ).read_text(encoding="utf-8")
    status_index = (
        REPO_ROOT / "docs" / "repository_status_index.md"
    ).read_text(encoding="utf-8")

    assert "docs/repository_status_index.md" in readme
    assert "docs/repository_status_index.md" in start_here
    for status in ("Supported", "Optional", "Quarantined", "Generated", "Archival"):
        assert f"`{status}`" in status_index
    assert "| `earCrawler/` | Supported |" in status_index
    assert "| `service/` | Supported |" in status_index
    assert "| `cli/` | Quarantined |" in status_index
    assert "| `build/`, `dist/`, `run/`, `runs/`, `earCrawler.egg-info/` | Generated |" in status_index
    assert "Default contributor path" in status_index


def test_repo_freezes_capability_matrix_and_api_search_status() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "RUNBOOK.md").read_text(encoding="utf-8")
    api_readme = (REPO_ROOT / "docs" / "api" / "readme.md").read_text(encoding="utf-8")
    capability_doc = (
        REPO_ROOT / "docs" / "capability_graduation_boundaries.md"
    ).read_text(encoding="utf-8")
    openapi_yaml_raw = (REPO_ROOT / "service" / "openapi" / "openapi.yaml").read_text(
        encoding="utf-8"
    )
    openapi_json_raw = (REPO_ROOT / "docs" / "api" / "openapi.json").read_text(
        encoding="utf-8"
    )
    postman_raw = (REPO_ROOT / "docs" / "api" / "postman_collection.json").read_text(
        encoding="utf-8"
    )
    openapi_json = json.loads(openapi_json_raw)
    postman = json.loads(postman_raw)

    assert "## Capability Matrix" in readme
    for status in ("Supported", "Optional", "Quarantined", "Proposal-only"):
        assert status in readme
    assert "EARCRAWLER_RETRIEVAL_MODE=hybrid" in readme
    assert "LLM_PROVIDER=local_adapter" in readme
    assert "docs/capability_graduation_boundaries.md" in readme
    assert "Quarantined runtime features include `/v1/search`" in runbook
    assert "EARCRAWLER_RETRIEVAL_MODE=hybrid" in runbook
    assert "docs/capability_graduation_boundaries.md" in runbook
    assert "kg_search_status_decision_2026-03-10.md" in readme
    assert "kg_search_status_decision_2026-03-10.md" in runbook
    assert "## 1. Text search" in capability_doc
    assert "## 2. Hybrid ranking" in capability_doc
    assert "## 3. KG expansion" in capability_doc
    assert "## 4. Local-adapter serving" in capability_doc
    assert "| `/v1/search` | Quarantined |" in api_readme
    assert "/v1/search" not in openapi_yaml_raw.split("\npaths:\n", 1)[1]
    assert "/v1/search" not in openapi_json.get("paths", {})
    assert all(
        "/v1/search" not in str(item.get("request", {}).get("url", {}).get("raw", ""))
        for item in postman.get("item", [])
    )


def test_kg_search_quarantine_decision_is_recorded_in_docs_and_code() -> None:
    decision_doc = (
        REPO_ROOT / "docs" / "kg_search_status_decision_2026-03-10.md"
    ).read_text(encoding="utf-8")
    search_router = (
        REPO_ROOT / "service" / "api_server" / "routers" / "search.py"
    ).read_text(encoding="utf-8")
    gate_doc = (REPO_ROOT / "docs" / "kg_quarantine_exit_gate.md").read_text(
        encoding="utf-8"
    )
    unquarantine_plan = (REPO_ROOT / "docs" / "kg_unquarantine_plan.md").read_text(
        encoding="utf-8"
    )

    assert "Decision: keep KG-backed search `Quarantined`." in decision_doc
    assert "No-Go for graduation" in decision_doc
    assert "docs/kg_unquarantine_plan.md" in decision_doc
    assert "kg_search_status_decision_2026-03-10.md" in search_router
    assert "KG-backed search quarantined" in search_router
    assert "kg_search_status_decision_2026-03-10.md" in gate_doc
    assert "does not govern" in gate_doc
    assert "EARCRAWLER_RETRIEVAL_MODE=hybrid" in gate_doc
    assert "kg_search_status_decision_2026-03-10.md" in unquarantine_plan
    assert "does not govern" in unquarantine_plan
    assert "LLM_PROVIDER=local_adapter" in unquarantine_plan


def test_windows_operator_guide_records_optional_vs_quarantined_capability_controls() -> None:
    operator_guide = (
        REPO_ROOT / "docs" / "ops" / "windows_single_host_operator.md"
    ).read_text(encoding="utf-8")
    service_docs = (REPO_ROOT / "service" / "docs" / "index.md").read_text(
        encoding="utf-8"
    )
    api_readme = (REPO_ROOT / "docs" / "api" / "readme.md").read_text(
        encoding="utf-8"
    )

    assert (REPO_ROOT / "scripts" / "optional-runtime-smoke.ps1").exists()
    assert "optional-runtime-smoke.ps1" in operator_guide
    assert "EARCRAWLER_RETRIEVAL_MODE" in operator_guide
    assert "LLM_PROVIDER" in operator_guide
    assert "EARCRAWLER_API_ENABLE_SEARCH" in operator_guide
    assert "EARCRAWLER_ENABLE_KG_EXPANSION" in operator_guide
    assert "EARCRAWLER_API_INSTANCE_COUNT" in operator_guide
    assert "EARCRAWLER_ALLOW_UNSUPPORTED_MULTI_INSTANCE=1" in operator_guide
    assert "docs/capability_graduation_boundaries.md" in operator_guide
    assert "EARCRAWLER_RETRIEVAL_MODE=hybrid" in service_docs
    assert "KG expansion remain `Quarantined`" in service_docs
    assert "runtime_contract" in service_docs
    assert "runtime_contract" in api_readme


def test_sample_ttl_pipeline_is_named_as_synthetic_fixture() -> None:
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "earCrawler.pipelines.build_ttl" not in ci_workflow
    assert "Synthetic Sample TTL Build and Gated Load (Quarantined)" in readme


def test_ci_uses_supported_evidence_path_gate() -> None:
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    release_workflow = (
        REPO_ROOT / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    ci_doc = (REPO_ROOT / "docs" / "ci.md").read_text(encoding="utf-8")
    api_smoke = (REPO_ROOT / "scripts" / "api-smoke.ps1").read_text(encoding="utf-8")
    optional_smoke = (REPO_ROOT / "scripts" / "optional-runtime-smoke.ps1").read_text(
        encoding="utf-8"
    )

    assert "Build synthetic sample TTL fixture bundle" not in ci_workflow
    assert "Supported corpus build gate" in ci_workflow
    assert "Supported corpus validate gate" in ci_workflow
    assert "Supported KG emit gate" in ci_workflow
    assert "Supported KG semantic gate" in ci_workflow
    assert "Supported API smoke gate" in ci_workflow
    assert "Optional runtime smoke gate" in ci_workflow
    assert "No-network RAG smoke gate" in ci_workflow
    assert "Supported API smoke parity" in release_workflow
    assert "Optional runtime smoke (search/KG gate validation)" in release_workflow
    assert "dist/api_smoke.json" in release_workflow
    assert "dist/optional_runtime_smoke.json" in release_workflow
    assert "-RequireCompleteEvidence" in release_workflow
    assert "-ApiSmokeReportPath dist/api_smoke.json" in release_workflow
    assert "tests/golden/test_phase2_golden_gate.py" in ci_workflow
    assert "Supported CI Evidence Path" in readme
    assert "supported evidence path" in ci_doc
    assert "optional runtime smoke" in ci_doc
    assert "ReportPath dist/api_smoke.json" in release_workflow
    assert "/v1/search" not in api_smoke
    assert "/v1/entities/" in api_smoke
    assert "/v1/lineage/" in api_smoke
    assert "/v1/sparql" in api_smoke
    assert "supported-api-smoke.v1" in api_smoke
    assert "search_default_off" in optional_smoke
    assert "search_opt_in_on" in optional_smoke
    assert "search_rollback_off" in optional_smoke


def test_cli_entrypoint_is_thin_and_uses_domain_registrars() -> None:
    main_cli = (REPO_ROOT / "earCrawler" / "cli" / "__main__.py").read_text(
        encoding="utf-8"
    )

    assert "register_corpus_commands(cli)" in main_cli
    assert "register_kg_commands(cli)" in main_cli
    assert "register_rag_commands(cli)" in main_cli
    assert "register_eval_commands(cli)" in main_cli
    assert "register_service_commands(cli)" in main_cli
    assert "def _register_shared_commands(" in main_cli
    assert main_cli.count("@click.command(") <= 2
    assert len(main_cli.splitlines()) < 220
