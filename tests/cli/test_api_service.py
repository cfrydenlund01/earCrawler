from __future__ import annotations

from pathlib import Path

from earCrawler.cli import api_service


def test_invoke_falls_back_to_windows_powershell(monkeypatch) -> None:
    fallback = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

    monkeypatch.setattr(api_service.platform, "system", lambda: "Windows")

    def fake_which(name: str) -> str | None:
        if name == "pwsh":
            return None
        if name == "powershell":
            return fallback
        return None

    monkeypatch.setattr(api_service.shutil, "which", fake_which)

    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], check: bool) -> None:
        captured["cmd"] = cmd

    monkeypatch.setattr(api_service.subprocess, "run", fake_run)

    api_service._invoke("api-start.ps1")

    cmd = captured["cmd"]
    assert cmd[0] == fallback
    assert Path(cmd[3]).name == "api-start.ps1"
