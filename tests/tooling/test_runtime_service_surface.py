from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

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
            raise RuntimeError(proc.stderr.strip() or f"rg failed with exit {proc.returncode}")
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
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
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
    for requirement in ("httpx", "keyring", "tenacity", "uvicorn"):
        assert any(
            str(dep).lower().startswith(requirement)
            for dep in dependencies
        ), f"Missing runtime dependency for packaged service import: {requirement}"


def test_repo_does_not_ship_container_runtime_artifacts() -> None:
    ci_workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release_workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

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
    assert "supported model-training, fine-tuning, agent, or quantization stack" in readme
    assert "docs/model_training_surface_adr.md" in readme


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


def test_repo_freezes_capability_matrix_and_api_search_status() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "RUNBOOK.md").read_text(encoding="utf-8")
    api_readme = (REPO_ROOT / "docs" / "api" / "readme.md").read_text(
        encoding="utf-8"
    )
    openapi_yaml = (REPO_ROOT / "service" / "openapi" / "openapi.yaml").read_text(
        encoding="utf-8"
    )
    openapi_json = (REPO_ROOT / "docs" / "api" / "openapi.json").read_text(
        encoding="utf-8"
    )
    postman = (REPO_ROOT / "docs" / "api" / "postman_collection.json").read_text(
        encoding="utf-8"
    )

    assert "## Capability Matrix" in readme
    for status in ("Supported", "Optional", "Quarantined", "Proposal-only"):
        assert status in readme
    assert "Quarantined runtime features include `/v1/search`" in runbook
    assert "| `/v1/search` | Quarantined |" in api_readme
    assert "Status: Quarantined" in openapi_yaml
    assert "quarantined" in openapi_json.lower()
    assert "quarantined /v1/search route" in postman


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
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    ci_doc = (REPO_ROOT / "docs" / "ci.md").read_text(encoding="utf-8")
    api_smoke = (REPO_ROOT / "scripts" / "api-smoke.ps1").read_text(encoding="utf-8")

    assert "Build synthetic sample TTL fixture bundle" not in ci_workflow
    assert "Supported corpus build gate" in ci_workflow
    assert "Supported corpus validate gate" in ci_workflow
    assert "Supported KG emit gate" in ci_workflow
    assert "Supported KG SHACL gate" in ci_workflow
    assert "Supported API smoke gate" in ci_workflow
    assert "No-network RAG smoke gate" in ci_workflow
    assert "tests/golden/test_phase2_golden_gate.py" in ci_workflow
    assert "Supported CI Evidence Path" in readme
    assert "supported evidence path" in ci_doc
    assert "/v1/search" not in api_smoke
    assert "/v1/entities/" in api_smoke
    assert "/v1/lineage/" in api_smoke
    assert "/v1/sparql" in api_smoke
