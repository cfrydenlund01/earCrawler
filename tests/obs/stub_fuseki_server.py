from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Tuple


class FusekiStubHandler(BaseHTTPRequestHandler):
    def log_message(
        self, format: str, *args: object
    ) -> None:  # pragma: no cover - suppress stderr
        return

    def do_GET(self) -> None:  # pragma: no cover - only used in CI
        if self.path.endswith("/$/ping"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:  # pragma: no cover - only used in CI
        if not self.path.endswith("/ds/query") and self.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        _ = self.rfile.read(length)
        payload = {
            "head": {"vars": ["ok"]},
            "results": {"bindings": [{"ok": {"type": "literal", "value": "1"}}]},
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/sparql-results+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(
    host: str = "127.0.0.1", port: int = 3030
) -> Tuple[str, int]:  # pragma: no cover - utility
    server = HTTPServer((host, port), FusekiStubHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return host, port


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()
