"""Simple file-based HTTP cache with ETag/Last-Modified support."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import requests


class HTTPCache:
    """Persist GET responses on disk keyed by URL and params."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, url: str, params: dict[str, str]) -> Path:
        key = url + "?" + urlencode(sorted(params.items()))
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.base_dir / f"{digest}.json"

    def get(
        self,
        session: requests.Session,
        url: str,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        """Return a cached response or fetch and store it."""

        headers = headers or {}
        path = self._key_path(url, params)
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
        resp = session.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 304 and path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            resp._content = cached["body"].encode("utf-8")
            resp.status_code = 200
            return resp

        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            data = {
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "body": str(resp.text) if resp.text is not None else "",
            }
            path.write_text(
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        return resp
