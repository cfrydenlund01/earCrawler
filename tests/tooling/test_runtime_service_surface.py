from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_NAME = "kg" + "_service"
ALLOWED_MATCHES = {
    Path("README.md"),
    Path("earCrawler/service/legacy") / (LEGACY_NAME + ".py"),
}


def _grep_files(pattern: str) -> set[Path]:
    if shutil.which("rg"):
        proc = subprocess.run(
            ["rg", "-l", pattern, "README.md", "docker", "service", "scripts", "earCrawler", "tests"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode not in (0, 1):
            raise RuntimeError(proc.stderr.strip() or f"rg failed with exit {proc.returncode}")
        return {Path(line.strip()) for line in proc.stdout.splitlines() if line.strip()}

    matches: set[Path] = set()
    for relative in (
        Path("README.md"),
        Path("docker"),
        Path("service"),
        Path("scripts"),
        Path("earCrawler"),
        Path("tests"),
    ):
        path = REPO_ROOT / relative
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
    dockerfile = (REPO_ROOT / "docker/api.Dockerfile").read_text(encoding="utf-8")
    assert "service.api_server.server:app" in dockerfile
    assert "earCrawler.service.sparql_service:app" not in dockerfile

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
