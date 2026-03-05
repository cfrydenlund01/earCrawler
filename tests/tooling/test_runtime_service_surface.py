from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_NAME = "kg" + "_service"
SEARCH_ROOTS = (
    Path("README.md"),
    Path("docker"),
    Path("container"),
    Path("service"),
    Path("scripts"),
    Path("earCrawler"),
    Path("tests"),
)
ALLOWED_MATCHES = {
    Path("README.md"),
    Path("earCrawler/service/legacy") / (LEGACY_NAME + ".py"),
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
    assert _grep_files(LEGACY_NAME) == ALLOWED_MATCHES


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
