from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.usefixtures("require_pwsh"), pytest.mark.enable_socket]

ROOT = Path(__file__).resolve().parents[2]


def run_ps(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["pwsh", "-File", str(ROOT / "scripts" / args[0])] + list(args[1:])
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=True, env=dict(os.environ))


def reserve_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return int(port)


def wait_for_port(port: int, timeout_seconds: float = 5.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.25)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for port {port} to accept connections.")


def test_api_start_recovers_managed_port_owner(tmp_path: Path) -> None:
    port = reserve_port()
    first_lifecycle = tmp_path / "api_start_first.json"
    second_lifecycle = tmp_path / "api_start_second.json"
    stop_lifecycle = tmp_path / "api_stop.json"

    try:
        run_ps("api-start.ps1", "-Host", "127.0.0.1", "-Port", str(port), "-LifecycleReportPath", str(first_lifecycle))
        run_ps("api-start.ps1", "-Host", "127.0.0.1", "-Port", str(port), "-LifecycleReportPath", str(second_lifecycle))
        payload = json.loads(second_lifecycle.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "api-start-lifecycle.v1"
        assert payload["preflight"]["status"] == "managed_recovery"
        assert payload["overall_status"] == "passed"
        assert payload["startup"]["status"] == "healthy"
    finally:
        run_ps("api-stop.ps1", "-LifecycleReportPath", str(stop_lifecycle), check=False)

    stop_payload = json.loads(stop_lifecycle.read_text(encoding="utf-8"))
    assert stop_payload["schema_version"] == "api-stop-lifecycle.v1"
    assert stop_payload["status"] in {"stopped", "stale_state_removed"}
    assert stop_payload["remaining_port_owners"] == []


def test_api_start_fails_fast_for_foreign_port_owner(tmp_path: Path) -> None:
    port = reserve_port()
    lifecycle = tmp_path / "api_start_conflict.json"
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_port(port)
        result = run_ps(
            "api-start.ps1",
            "-Host",
            "127.0.0.1",
            "-Port",
            str(port),
            "-LifecycleReportPath",
            str(lifecycle),
            check=False,
        )
        assert result.returncode != 0
        payload = json.loads(lifecycle.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "api-start-lifecycle.v1"
        assert payload["preflight"]["status"] == "foreign_conflict"
        assert payload["overall_status"] == "failed"
        assert payload["preflight"]["occupied_port"] is True
        assert payload["preflight"]["owners"]
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_api_stop_recovers_orphan_managed_port_owner(tmp_path: Path) -> None:
    port = reserve_port()
    start_lifecycle = tmp_path / "api_start.json"
    stop_lifecycle = tmp_path / "api_stop_orphan.json"
    pid_file = ROOT / "kg" / "reports" / "api.pid"
    state_file = ROOT / "kg" / "reports" / "api.process.json"

    try:
        run_ps(
            "api-start.ps1",
            "-Host",
            "127.0.0.1",
            "-Port",
            str(port),
            "-LifecycleReportPath",
            str(start_lifecycle),
        )
        pid_file.unlink(missing_ok=True)
        state_file.unlink(missing_ok=True)

        run_ps(
            "api-stop.ps1",
            "-Port",
            str(port),
            "-LifecycleReportPath",
            str(stop_lifecycle),
        )
        payload = json.loads(stop_lifecycle.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "api-stop-lifecycle.v1"
        assert payload["requested_port"] == port
        assert payload["status"] == "stopped"
        assert payload["remaining_port_owners"] == []
    finally:
        run_ps("api-stop.ps1", "-Port", str(port), check=False)
