"""Simple file-based HTTP cache with ETag/Last-Modified support."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlencode

import requests

try:  # pragma: no cover - optional dependency in tests
    import vcr.stubs
except Exception:  # pragma: no cover - vcr not installed
    pass
else:  # pragma: no cover - executed in test env
    if not hasattr(vcr.stubs.VCRHTTPResponse, "version_string"):
        def _version_string(self: object) -> str:
            version = getattr(self, "version", None)
            if isinstance(version, bytes):
                try:
                    return version.decode("ascii")
                except Exception:
                    return "HTTP/1.1"
            if isinstance(version, str) and version:
                return version
            return "HTTP/1.1"

        vcr.stubs.VCRHTTPResponse.version_string = property(_version_string)  # type: ignore[attr-defined]


class HTTPCache:
    """Persist GET responses on disk keyed by URL, params, and selected headers."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(
        self,
        url: str,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        vary_headers: Iterable[str],
    ) -> Path:
        normalized_params = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
        header_map = {str(k).lower(): str(v) for k, v in headers.items()}
        header_components = []
        for name in vary_headers:
            key = str(name).lower()
            header_components.append(f"{key}={header_map.get(key, '')}")
        key_source = "||".join(filter(None, [url, normalized_params, "|".join(header_components)]))
        digest = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        return self.base_dir / f"{digest}.json"

    def get(
        self,
        session: requests.Session,
        url: str,
        params: Mapping[str, str],
        *,
        headers: Mapping[str, str] | None = None,
        vary_headers: Iterable[str] | None = None,
    ) -> requests.Response:
        """Return a cached response or fetch and store it."""

        request_headers = dict(headers or {})
        vary = tuple(vary_headers or ())
        path = self._key_path(url, params, request_headers, vary)
        cache_hit = path.exists()
        if cache_hit:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("etag"):
                request_headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                request_headers["If-Modified-Since"] = cached["last_modified"]
        resp = session.get(url, params=params, headers=request_headers, timeout=10)
        setattr(resp, "from_cache", False)
        if resp.status_code == 304 and cache_hit:
            cached = json.loads(path.read_text(encoding="utf-8"))
            resp._content = cached["body"].encode("utf-8")
            resp.status_code = 200
            setattr(resp, "from_cache", True)
            return resp

        if resp.status_code == 200 and cache_hit:
            setattr(resp, "from_cache", True)

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

    def clear(self) -> None:
        for path in self.base_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                continue
