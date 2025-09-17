from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HEALTH_SCRIPT = ROOT / "bundle" / "scripts" / "bundle-health.ps1"

pytestmark = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell required")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Handler(BaseHTTPRequestHandler):
    ok = True

    def do_GET(self):
        if self.path.startswith("/$/ping"):
            if self.ok:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(500)
                self.end_headers()
        elif self.path.startswith("/ds/sparql"):
            self.send_response(200)
            self.send_header("Content-Type", "application/sparql-results+json")
            self.end_headers()
            payload = {
                "head": {"vars": ["count"]},
                "results": {"bindings": [{"count": {"type": "literal", "value": "1"}}]},
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        return


def _start_server(port: int, ok: bool = True) -> ThreadingHTTPServer:
    _Handler.ok = ok
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _write_config(tmp: Path, port: int) -> None:
    (tmp / "config").mkdir(parents=True, exist_ok=True)
    config_text = f"""
version: 1
fuseki:
  host: 127.0.0.1
  port: {port}
  timeout_seconds: 5
  log_dir: fuseki/logs
  jvm_opts: ""
  health_query: "SELECT (COUNT(*) AS ?count) WHERE {{ ?s ?p ?o }} LIMIT 1"
dataset:
  assembler: fuseki/tdb2-readonly.ttl
"""
    (tmp / "config" / "bundle_config.yml").write_text(config_text.strip())


def test_health_success(tmp_path):
    port = _free_port()
    server = _start_server(port, ok=True)
    try:
        _write_config(tmp_path, port)
        subprocess.run(["pwsh", "-File", str(HEALTH_SCRIPT), "-Path", str(tmp_path)], check=True)
    finally:
        server.shutdown()


def test_health_failure(tmp_path):
    port = _free_port()
    _write_config(tmp_path, port)
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(["pwsh", "-File", str(HEALTH_SCRIPT), "-Path", str(tmp_path), "-TimeoutSeconds", "2"], check=True)
