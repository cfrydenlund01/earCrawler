from __future__ import annotations

"""Runtime fetcher for eCFR snapshots (network gated).

This module intentionally lives behind EARCRAWLER_ALLOW_NETWORK=1 so tests/CI
don't silently hit the network. It fetches section HTML via the eCFR renderer
API, parses section-level text, and writes an offline snapshot payload + bound
manifest (offline-snapshot.v1).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Iterable, Sequence

import requests
from bs4 import BeautifulSoup

from earCrawler.rag.offline_snapshot_manifest import MANIFEST_VERSION, compute_sha256_hex


def _require_network() -> None:
    if os.getenv("EARCRAWLER_ALLOW_NETWORK") != "1":
        raise RuntimeError(
            "Network access disabled; set EARCRAWLER_ALLOW_NETWORK=1 to fetch eCFR snapshots."
        )


@dataclass(frozen=True)
class EcfrSnapshotRecord:
    section_id: str
    heading: str
    text: str
    source_ref: str
    url: str


def _utc_now_iso8601() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _renderer_url(*, title: str, date: str, part: str | None = None) -> str:
    base = f"https://www.ecfr.gov/api/renderer/v1/content/enhanced/{date}/title-{title}"
    if part:
        return f"{base}?part={part}"
    return base


def _extract_section_url(heading_node) -> str:
    if heading_node is None:
        return ""
    meta = heading_node.attrs.get("data-hierarchy-metadata")
    if not meta:
        return ""
    try:
        payload = json.loads(str(meta))
    except Exception:
        return ""
    path = str(payload.get("path") or "").strip()
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return "https://www.ecfr.gov" + path


def _iter_sections_from_html(html: str, *, source_ref: str) -> Iterable[EcfrSnapshotRecord]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("div.section"):
        raw_id = str(node.get("id") or "").strip()
        if not raw_id:
            continue

        heading_node = node.find(["h2", "h3", "h4", "h5"])
        heading = heading_node.get_text(" ", strip=True) if heading_node else ""
        url = _extract_section_url(heading_node)

        # Prefer block-aware extraction to avoid turning inline spans into line-starts,
        # which can confuse marker parsing in the chunker.
        blocks: list[str] = []
        for tag in node.find_all(["p", "li"], recursive=True):
            block = tag.get_text(" ", strip=True)
            if block:
                blocks.append(block)
        text = "\n\n".join(blocks).strip()
        if not text:
            # Fallback: stable but less semantically meaningful.
            strings = [s for s in node.stripped_strings]
            if heading and strings and strings[0] == heading:
                strings = strings[1:]
            text = " ".join(strings).strip()
        if not text:
            continue

        yield EcfrSnapshotRecord(
            section_id=f"§ {raw_id}",
            heading=heading,
            text=text,
            source_ref=source_ref,
            url=url,
        )


def _write_jsonl(path: Path, records: Sequence[EcfrSnapshotRecord]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for rec in records:
            handle.write(
                json.dumps(
                    {
                        "section_id": rec.section_id,
                        "heading": rec.heading,
                        "text": rec.text,
                        "source_ref": rec.source_ref,
                        "url": rec.url,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )


def _write_manifest(
    *,
    manifest_path: Path,
    snapshot_id: str,
    title: str,
    parts: Sequence[str],
    payload_path: Path,
    created_at: str,
    owner: str,
    upstream: str,
    approved_by: str,
    approved_at: str,
) -> None:
    payload_rel = Path(payload_path.name)
    payload_bytes = payload_path.stat().st_size
    sha256 = compute_sha256_hex(payload_path)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "source": {
            "owner": owner,
            "upstream": upstream,
            "approved_by": approved_by,
            "approved_at": approved_at,
        },
        "scope": {"titles": [str(title)], "parts": [str(p) for p in parts]},
        "payload": {"path": str(payload_rel), "sha256": sha256, "size_bytes": int(payload_bytes)},
    }
    Path(manifest_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def fetch_ecfr_snapshot(
    out_path: Path,
    *,
    title: str = "15",
    date: str | None = None,
    parts: Sequence[str] | None = None,
    snapshot_id: str | None = None,
    manifest_path: Path | None = None,
    owner: str | None = None,
    approved_by: str | None = None,
    upstream: str = "ecfr.gov renderer API (enhanced HTML)",
) -> tuple[Path, Path]:
    """Fetch an offline snapshot payload + manifest.

    - Writes JSONL payload to out_path (UTF-8, LF-only newlines).
    - Writes a bound manifest (offline-snapshot.v1) next to the payload unless overridden.
    - Requires EARCRAWLER_ALLOW_NETWORK=1.
    """

    _require_network()

    resolved_title = str(title).strip() or "15"
    resolved_date = (date or "current").strip() or "current"
    requested_parts = [str(p).strip() for p in (parts or []) if str(p).strip()]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_manifest_path = Path(manifest_path) if manifest_path else (out_path.parent / "manifest.json")

    created_at = _utc_now_iso8601()
    resolved_snapshot_id = (snapshot_id or out_path.parent.name or f"ecfr-{created_at}").strip()
    username = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
    resolved_owner = (owner or username).strip() or "unknown"
    resolved_approved_by = (approved_by or resolved_owner).strip() or "unknown"
    resolved_approved_at = created_at

    session = requests.Session()
    session.headers.update({"User-Agent": "earCrawler/ecfr-fetch"})

    records: list[EcfrSnapshotRecord] = []
    if requested_parts:
        for part in requested_parts:
            url = _renderer_url(title=resolved_title, date=resolved_date, part=part)
            resp = session.get(url, timeout=60)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to fetch Title {resolved_title} Part {part} "
                    f"(HTTP {resp.status_code}) from {url}"
                )
            part_records = list(
                _iter_sections_from_html(
                    resp.text,
                    source_ref=f"ecfr:{resolved_date}:title{resolved_title}:part{part}",
                )
            )
            if not part_records:
                raise RuntimeError(f"No sections parsed for Title {resolved_title} Part {part} from {url}")
            records.extend(part_records)
    else:
        # Backwards-compatible: allow fetching the entire title (can be large).
        url = _renderer_url(title=resolved_title, date=resolved_date)
        resp = session.get(url, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch Title {resolved_title} (HTTP {resp.status_code}) from {url}"
            )
        records = list(
            _iter_sections_from_html(resp.text, source_ref=f"ecfr:{resolved_date}:title{resolved_title}")
        )
        if not records:
            raise RuntimeError(f"No sections parsed for Title {resolved_title} from {url}")

    records = sorted(records, key=lambda r: r.section_id)
    _write_jsonl(out_path, records)
    _write_manifest(
        manifest_path=resolved_manifest_path,
        snapshot_id=resolved_snapshot_id,
        title=resolved_title,
        parts=requested_parts,
        payload_path=out_path,
        created_at=created_at,
        owner=resolved_owner,
        upstream=upstream,
        approved_by=resolved_approved_by,
        approved_at=resolved_approved_at,
    )
    return out_path, resolved_manifest_path


__all__ = ["fetch_ecfr_snapshot", "EcfrSnapshotRecord"]
