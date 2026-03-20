import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = [pytest.mark.usefixtures("require_pwsh"), pytest.mark.enable_socket]

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "iis-front-door-smoke.ps1"
CONFIG = ROOT / "scripts" / "ops" / "iis-earcrawler-front-door.web.config.example"


def run_smoke(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["pwsh", "-File", str(SCRIPT)] + list(args)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=dict(os.environ),
        check=check,
        capture_output=True,
        text=True,
    )


class _FrontDoorHandler(BaseHTTPRequestHandler):
    request_id_enabled = True

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            if self.request_id_enabled:
                self.send_header("X-Request-Id", "req-123")
            self.send_header("X-Subject", "proxy")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return

        if self.path.startswith("/v1/search") or self.path == "/docs":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not published")
            return

        self.send_response(500)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.fixture
def front_door_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FrontDoorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_iis_front_door_smoke_script_passes_against_expected_proxy_shape(
    tmp_path: Path, front_door_server: ThreadingHTTPServer
) -> None:
    report = tmp_path / "front-door.txt"
    json_report = tmp_path / "front-door.json"
    base_url = f"http://127.0.0.1:{front_door_server.server_port}"

    run_smoke(
        "-BaseUrl",
        base_url,
        "-ExpectedSubject",
        "proxy",
        "-ReportPath",
        str(report),
        "-JsonReportPath",
        str(json_report),
    )

    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "iis-front-door-smoke.v1"
    assert payload["health"]["status_code"] == 200
    assert payload["health"]["request_id_present"] is True
    assert payload["health"]["subject_ok"] is True
    assert payload["quarantined_path"]["status_code"] == 404
    assert payload["unpublished_path"]["status_code"] == 404
    assert payload["overall_status"] == "passed"


def test_iis_front_door_smoke_script_fails_when_request_id_is_missing(
    tmp_path: Path, front_door_server: ThreadingHTTPServer
) -> None:
    report = tmp_path / "front-door.txt"
    json_report = tmp_path / "front-door.json"
    base_url = f"http://127.0.0.1:{front_door_server.server_port}"

    original = _FrontDoorHandler.request_id_enabled
    _FrontDoorHandler.request_id_enabled = False
    try:
        result = run_smoke(
            "-BaseUrl",
            base_url,
            "-ExpectedSubject",
            "proxy",
            "-ReportPath",
            str(report),
            "-JsonReportPath",
            str(json_report),
            check=False,
        )
    finally:
        _FrontDoorHandler.request_id_enabled = original

    assert result.returncode != 0
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["health"]["request_id_present"] is False
    assert payload["overall_status"] == "failed"


def test_iis_front_door_example_keeps_loopback_backend_and_excludes_search() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "http://127.0.0.1:9001/{R:1}" in text
    assert "v1/rag/answer" in text
    assert "v1/search" not in text
