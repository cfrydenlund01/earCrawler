from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build-offline-bundle.ps1"
FIRST_RUN_SCRIPT = ROOT / "dist" / "offline_bundle" / "scripts" / "bundle-first-run.ps1"

pytestmark = pytest.mark.usefixtures("require_pwsh")


def _run_build() -> Path:
    subprocess.run(["pwsh", "-File", str(BUILD_SCRIPT)], check=True, cwd=ROOT)
    return ROOT / "dist" / "offline_bundle"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_first_run_bootstrap(tmp_path):
    bundle = _run_build()

    tools_jena = bundle / "tools" / "jena" / "bin"
    tools_jena.mkdir(parents=True, exist_ok=True)
    loader = tools_jena / "tdb2_tdbloader"
    _write_executable(
        loader,
        """#!/usr/bin/env python3
import argparse
import pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--loc', required=True)
parser.add_argument('--nquads', action='store_true')
parser.add_argument('dataset')
args = parser.parse_args()
path = pathlib.Path(args.loc)
path.mkdir(parents=True, exist_ok=True)
(path / 'loader.ok').write_text('loaded')
""",
    )

    tools_fuseki = bundle / "tools" / "fuseki"
    tools_fuseki.mkdir(parents=True, exist_ok=True)
    fuseki = tools_fuseki / "fuseki-server"
    _write_executable(
        fuseki,
        """#!/usr/bin/env python3
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/$/ping'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        elif self.path.startswith('/ds/sparql'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/sparql-results+json')
            self.end_headers()
            payload = {
                'head': {'vars': ['count']},
                'results': {'bindings': [{'count': {'type': 'literal', 'value': '1'}}]},
            }
            self.wfile.write(json.dumps(payload).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs):
        return

def main(port: int) -> None:
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    port = 3030
    for idx, value in enumerate(sys.argv):
        if value == '--port' and idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])
    main(port)
""",
    )

    # Provide fake java on PATH
    fake_java_dir = tmp_path / "bin"
    fake_java_dir.mkdir()
    fake_java = fake_java_dir / "java"
    _write_executable(
        fake_java, "#!/usr/bin/env python3\nprint('java version " "0" "')\n"
    )

    env = os.environ.copy()
    env["PATH"] = str(fake_java_dir) + os.pathsep + env.get("PATH", "")

    subprocess.run(
        ["pwsh", "-File", str(FIRST_RUN_SCRIPT), "-Path", str(bundle)],
        check=True,
        env=env,
        cwd=ROOT,
    )
    marker = bundle / "fuseki" / "databases" / "first_run.ok"
    assert marker.exists()
    report = bundle / "kg" / "reports" / "bundle-smoke.txt"
    contents = report.read_text().splitlines()
    assert any(line.startswith("timestamp=") for line in contents)

    # Idempotent second run
    subprocess.run(
        ["pwsh", "-File", str(FIRST_RUN_SCRIPT), "-Path", str(bundle)],
        check=True,
        env=env,
        cwd=ROOT,
    )
    assert marker.read_text().strip()
    assert (bundle / "fuseki" / "databases" / "tdb2" / "loader.ok").exists()
